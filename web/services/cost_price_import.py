import csv
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction
from django.db.models import Count
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from web.models import Product


ALLOWED_EXTENSIONS = {'.csv', '.xlsx'}
HEADER_NAMES = {'название', 'название товара', 'товар'}
HEADER_COSTS = {'себестоимость', 'себестоимость товара'}
MAX_COST_PRICE = Decimal('99999999.99')
MAX_FILE_ROWS = 5000


class CostPriceImportError(Exception):
    pass


def normalize_product_name(value) -> str:
    text = unicodedata.normalize('NFKC', str(value or ''))
    return re.sub(r'\s+', ' ', text).strip().casefold()


def parse_cost_price(value, row_number: int) -> Decimal:
    if value is None:
        raise CostPriceImportError(f'Строка {row_number}: себестоимость не указана.')

    normalized = str(value).strip().replace('\xa0', '').replace(' ', '').replace('₽', '').replace(',', '.')
    try:
        cost_price = Decimal(normalized).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise CostPriceImportError(
            f'Строка {row_number}: некорректная себестоимость «{value}».'
        ) from None

    if cost_price <= 0:
        raise CostPriceImportError(f'Строка {row_number}: себестоимость должна быть больше нуля.')
    if cost_price > MAX_COST_PRICE:
        raise CostPriceImportError(f'Строка {row_number}: себестоимость слишком велика.')
    return cost_price


def read_uploaded_rows(uploaded_file) -> list[tuple]:
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise CostPriceImportError('Поддерживаются только файлы .xlsx и .csv.')

    try:
        if extension == '.xlsx':
            workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
            worksheet = workbook.active
            rows = []
            for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                if row_number > MAX_FILE_ROWS:
                    raise CostPriceImportError(f'В файле должно быть не больше {MAX_FILE_ROWS} строк.')
                rows.append(tuple(row[:2]))
            return rows

        content = uploaded_file.read()
        decoded = None
        for encoding in ('utf-8-sig', 'cp1251'):
            try:
                decoded = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise CostPriceImportError('Не удалось определить кодировку CSV. Используйте UTF-8 или CP1251.')

        sample = decoded[:4096]
        delimiter = ';' if ';' in sample else ','
        rows = []
        for row_number, row in enumerate(csv.reader(io.StringIO(decoded), delimiter=delimiter), start=1):
            if row_number > MAX_FILE_ROWS:
                raise CostPriceImportError(f'В файле должно быть не больше {MAX_FILE_ROWS} строк.')
            rows.append(tuple(row[:2]))
        return rows
    except (InvalidFileException, OSError, ValueError) as exc:
        raise CostPriceImportError(f'Не удалось прочитать файл: {exc}') from exc


def parsed_cost_rows(uploaded_file) -> list[dict]:
    raw_rows = read_uploaded_rows(uploaded_file)
    rows = []

    for row_number, values in enumerate(raw_rows, start=1):
        name = values[0] if len(values) > 0 else None
        cost_value = values[1] if len(values) > 1 else None
        if not str(name or '').strip() and not str(cost_value or '').strip():
            continue

        normalized_name = normalize_product_name(name)
        normalized_cost_header = normalize_product_name(cost_value)
        if not rows and normalized_name in HEADER_NAMES and normalized_cost_header in HEADER_COSTS:
            continue

        if not normalized_name:
            rows.append({
                'row_number': row_number,
                'name': '',
                'cost_price': str(cost_value or ''),
                'status': 'invalid',
                'message': 'Название товара не указано.',
            })
            continue

        try:
            cost_price = parse_cost_price(cost_value, row_number)
        except CostPriceImportError as exc:
            rows.append({
                'row_number': row_number,
                'name': str(name).strip(),
                'cost_price': str(cost_value or ''),
                'status': 'invalid',
                'message': str(exc),
            })
            continue

        rows.append({
            'row_number': row_number,
            'name': str(name).strip(),
            'normalized_name': normalized_name,
            'cost_price': str(cost_price),
        })

    if not rows:
        raise CostPriceImportError('В файле нет строк с товарами.')
    return rows


def build_import_preview(uploaded_file) -> dict:
    rows = parsed_cost_rows(uploaded_file)
    name_counts = {}
    for row in rows:
        normalized_name = row.get('normalized_name')
        if normalized_name:
            name_counts[normalized_name] = name_counts.get(normalized_name, 0) + 1
    duplicate_names = {name for name, count in name_counts.items() if count > 1}

    targets = (
        Product.objects.filter(
            ozon_quantity__gt=0,
            quantity=0,
            cost_price=Decimal('0.00'),
        )
        .annotate(batch_count=Count('batches'))
        .filter(batch_count=0)
    )
    targets_by_name = {}
    for product in targets:
        targets_by_name.setdefault(normalize_product_name(product.name), []).append(product)

    all_products_by_name = {}
    for product in Product.objects.only('id', 'article', 'name'):
        all_products_by_name.setdefault(normalize_product_name(product.name), []).append(product)

    preview_rows = []
    for row in rows:
        if row.get('status') == 'invalid':
            preview_rows.append(row)
            continue

        normalized_name = row['normalized_name']
        if normalized_name in duplicate_names:
            row.update(
                status='duplicate',
                message='Название повторяется в загруженном файле.',
            )
            preview_rows.append(row)
            continue

        matches = targets_by_name.get(normalized_name, [])
        if len(matches) == 1:
            product = matches[0]
            row.update(
                status='matched',
                message='Готов к обновлению.',
                product_id=product.id,
                article=product.article,
                old_purchase_price=str(product.purchase_price),
                old_delivery_cost=str(product.delivery_cost),
                old_cost_price=str(product.cost_price),
            )
        elif len(matches) > 1:
            row.update(
                status='ambiguous',
                message='Найдено несколько подходящих OZON-товаров.',
            )
        elif normalized_name in all_products_by_name:
            articles = ', '.join(product.article for product in all_products_by_name[normalized_name][:5])
            row.update(
                status='protected',
                article=articles,
                message='Товар найден, но защищён условиями импорта.',
            )
        else:
            row.update(
                status='not_found',
                message='Товар с таким названием не найден.',
            )
        preview_rows.append(row)

    summary = {
        status: sum(row.get('status') == status for row in preview_rows)
        for status in ('matched', 'protected', 'not_found', 'ambiguous', 'duplicate', 'invalid')
    }
    return {
        'file_name': Path(uploaded_file.name).name[:255],
        'rows': preview_rows,
        'summary': summary,
    }


def product_is_import_target(product: Product) -> bool:
    return (
        product.ozon_quantity > 0
        and product.quantity == 0
        and product.cost_price == Decimal('0.00')
        and not product.batches.exists()
    )


@transaction.atomic
def apply_cost_price_import(preview: dict) -> list[tuple[Product, dict]]:
    matched_rows = [row for row in preview.get('rows', []) if row.get('status') == 'matched']
    if not matched_rows:
        raise CostPriceImportError('Нет товаров, готовых к обновлению.')

    products = {
        product.id: product
        for product in Product.objects.select_for_update().filter(
            id__in=[row['product_id'] for row in matched_rows]
        )
    }
    for row in matched_rows:
        product = products.get(row['product_id'])
        if (
            product is None
            or normalize_product_name(product.name) != row['normalized_name']
            or str(product.purchase_price) != row['old_purchase_price']
            or str(product.delivery_cost) != row['old_delivery_cost']
            or str(product.cost_price) != row['old_cost_price']
            or not product_is_import_target(product)
        ):
            raise CostPriceImportError(
                f'Товар «{row["name"]}» изменился после предпросмотра. Создайте импорт заново.'
            )

    for row in matched_rows:
        product = products[row['product_id']]
        product.purchase_price = Decimal(row['cost_price'])
        product.delivery_cost = Decimal('0.00')
        product.save()
    return [(products[row['product_id']], row) for row in matched_rows]
