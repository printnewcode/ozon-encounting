import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .forms import SalesUploadForm, SupplyUploadForm
from .models import Product, SaleRecord


MONEY_HEADERS = ('Стоимость в закупке', 'Доставка', 'Себестоимость', 'Доход', 'Прибыль')
DATE_HEADER = 'Дата продажи'
CSV_ENCODINGS = ('utf-8-sig', 'utf-8', 'cp1251')
MAX_VISIBLE_WARNINGS = 5


def export_filename(name: str) -> str:
    timestamp = datetime.now().strftime('%Y-%m-%d')
    return f'{name}_{timestamp}.xlsx'


def workbook_response(workbook: Workbook, filename: str) -> HttpResponse:
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


def style_export_sheet(sheet, widths: list[int]) -> None:
    header_fill = PatternFill('solid', fgColor='0EA5E9')
    header_font = Font(color='FFFFFF', bold=True)
    border_color = 'E5E7EB'
    thin_border = Border(
        left=Side(style='thin', color=border_color),
        right=Side(style='thin', color=border_color),
        top=Side(style='thin', color=border_color),
        bottom=Side(style='thin', color=border_color),
    )

    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions

    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(vertical='center')

    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    for row in sheet.iter_rows():
        sheet.row_dimensions[row[0].row].height = 22

    for column in sheet.iter_cols():
        header = column[0].value
        for cell in column[1:]:
            if header in MONEY_HEADERS:
                cell.number_format = '#,##0.00'
            elif header == DATE_HEADER:
                cell.number_format = 'DD.MM.YYYY'


def parse_decimal(value, field_name: str, row_number: int) -> Decimal:
    try:
        return Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Строка {row_number}: некорректное значение поля «{field_name}»: {value!r}")


def parse_positive_int(value, field_name: str, row_number: int, default: int | None = None) -> int:
    if value in (None, '') and default is not None:
        return default
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Строка {row_number}: некорректное значение поля «{field_name}»: {value!r}")
    if quantity <= 0:
        raise ValueError(f"Строка {row_number}: поле «{field_name}» должно быть больше 0")
    return quantity


def is_header_or_empty_article(value) -> bool:
    article = str(value).strip()
    return not article or article.lower() in {'nan', 'article', 'артикул'}


def values_differ(left, right) -> bool:
    return str(left).strip() != str(right).strip()


def add_limited_warning(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def show_import_warnings(request, warnings: list[str]) -> None:
    if not warnings:
        return
    visible_warnings = warnings[:MAX_VISIBLE_WARNINGS]
    suffix = f" Еще предупреждений: {len(warnings) - MAX_VISIBLE_WARNINGS}." if len(warnings) > MAX_VISIBLE_WARNINGS else ''
    messages.warning(request, " ".join(visible_warnings) + suffix)


def sale_cost_price(sale: SaleRecord) -> Decimal:
    if sale.profit is not None:
        return sale.income - sale.profit
    return sale.product.cost_price


def parse_file(file) -> pd.DataFrame:
    """Parse uploaded Excel/CSV file into a normalized DataFrame."""
    if Path(file.name).suffix.lower() == '.csv':
        content = file.read()

        for encoding in CSV_ENCODINGS:
            try:
                decoded_content = content.decode(encoding)
                separator = ';' if ';' in decoded_content else ','
                df = pd.read_csv(io.StringIO(decoded_content), sep=separator)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Не удалось определить кодировку файла. Используйте UTF-8 или CP1251.")
    else:
        df = pd.read_excel(file)

    df.columns = df.columns.astype(str).str.strip()
    return df.fillna('')


def upload_supply(request):
    if request.method == 'POST':
        form = SupplyUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            try:
                df = parse_file(file)

                products_created = 0
                warnings = []
                seen_articles = set()
                with transaction.atomic():
                    for index, row in df.iterrows():
                        row_number = index + 1
                        if df.shape[1] < 5:
                            raise ValueError("Файл поставки должен содержать минимум 5 колонок.")

                        article = str(row.iloc[0]).strip()
                        if is_header_or_empty_article(article):
                            continue
                        if article in seen_articles:
                            add_limited_warning(
                                warnings,
                                f"Артикул {article} встречается в файле поставки несколько раз; количество будет суммировано.",
                            )
                        seen_articles.add(article)

                        name = str(row.iloc[1]).strip()
                        if not name:
                            raise ValueError(f"Строка {row_number}: название товара не может быть пустым")

                        purchase_price = parse_decimal(row.iloc[2], 'Стоимость в закупке', row_number)
                        delivery_cost = parse_decimal(row.iloc[3], 'Доставка', row_number)
                        quantity_value = row.iloc[5] if df.shape[1] > 5 else row.iloc[4]
                        quantity = parse_positive_int(quantity_value, 'Количество', row_number)

                        product, created = Product.objects.select_for_update().get_or_create(
                            article=article,
                            defaults={
                                'name': name,
                                'purchase_price': purchase_price,
                                'delivery_cost': delivery_cost,
                                'quantity': quantity,
                                'status': 'in_stock',
                            },
                        )
                        if not created:
                            if values_differ(product.name, name):
                                add_limited_warning(
                                    warnings,
                                    f"Для артикула {article} название в файле отличается от базы: «{name}» / «{product.name}».",
                                )
                            if product.purchase_price != purchase_price or product.delivery_cost != delivery_cost:
                                add_limited_warning(
                                    warnings,
                                    f"Для артикула {article} изменена цена поставки или доставки; себестоимость пересчитана.",
                                )
                            product.purchase_price = purchase_price
                            product.delivery_cost = delivery_cost
                            product.quantity += quantity
                            product.status = 'in_stock'
                            product.save()

                        products_created += 1

                messages.success(request, f'Успешно загружено {products_created} товаров из поставки.')
                show_import_warnings(request, warnings)
                return redirect('product_list')
            except Exception as exc:
                messages.error(request, f'Ошибка при обработке файла: {exc}')
    else:
        form = SupplyUploadForm()

    return render(request, 'web/upload_supply.html', {'form': form})


def upload_sales(request):
    if request.method == 'POST':
        form = SalesUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            sale_type = form.cleaned_data['sale_type']
            try:
                df = parse_file(file)

                sales_created = 0
                errors = []
                warnings = []
                seen_articles = set()
                with transaction.atomic():
                    for index, row in df.iterrows():
                        row_number = index + 1
                        if df.shape[1] < 3:
                            raise ValueError("Файл продаж должен содержать минимум 3 колонки.")

                        article = str(row.iloc[0]).strip()
                        if is_header_or_empty_article(article):
                            continue
                        if article in seen_articles:
                            add_limited_warning(
                                warnings,
                                f"Артикул {article} встречается в файле продаж несколько раз; продажи будут суммированы.",
                            )
                        seen_articles.add(article)

                        uploaded_name = str(row.iloc[1]).strip() if df.shape[1] > 1 else ''

                        income = parse_decimal(row.iloc[2], 'Доход', row_number)
                        quantity_value = row.iloc[3] if df.shape[1] > 3 else None
                        quantity_sold = parse_positive_int(quantity_value, 'Количество', row_number, default=1)

                        try:
                            product = Product.objects.select_for_update().get(article=article)
                        except Product.DoesNotExist:
                            errors.append(f"Товар с артикулом {article} не найден в базе.")
                            continue

                        if uploaded_name and values_differ(product.name, uploaded_name):
                            add_limited_warning(
                                warnings,
                                f"Для артикула {article} название в файле отличается от базы: «{uploaded_name}» / «{product.name}».",
                            )
                        if quantity_sold > product.quantity:
                            add_limited_warning(
                                warnings,
                                f"По артикулу {article} продано {quantity_sold}, а в остатке было {product.quantity}; остаток обнулен.",
                            )

                        product.quantity -= quantity_sold
                        if product.quantity <= 0:
                            product.status = 'sold'
                            product.quantity = 0
                        elif sale_type == 'ozon':
                            product.status = 'in_sale'
                        product.save()

                        for _ in range(quantity_sold):
                            SaleRecord.objects.create(
                                product=product,
                                sale_type=sale_type,
                                income=income,
                            )
                        sales_created += quantity_sold

                if sales_created > 0:
                    messages.success(request, f'Успешно загружено {sales_created} записей о продажах.')
                if errors:
                    message = "Некоторые товары не были найдены: " + ", ".join(errors[:5])
                    messages.warning(request, message + ("..." if len(errors) > 5 else ""))
                show_import_warnings(request, warnings)

                return redirect('product_list')
            except Exception as exc:
                messages.error(request, f'Ошибка при обработке файла: {exc}')
    else:
        form = SalesUploadForm()

    return render(request, 'web/upload_sales.html', {'form': form})


def product_list(request):
    groups_dict = {}
    status_order = {
        'in_stock': 0,
        'in_sale': 1,
        'sold': 2,
    }

    def get_group(article, status_key, name, status_label):
        group_key = (article, status_key)
        if group_key not in groups_dict:
            groups_dict[group_key] = {
                'article': article,
                'name': name,
                'status_key': status_key,
                'status_label': status_label,
                'rows': [],
                'count': 0,
                'total_income': Decimal('0'),
                'total_profit': Decimal('0'),
                'has_sales': False,
                'sort_status': status_order.get(status_key, 99),
            }
        return groups_dict[group_key]

    unsold = Product.objects.filter(status__in=['in_stock', 'in_sale']).order_by('article', 'created_at')
    for product in unsold:
        group = get_group(product.article, product.status, product.name, product.get_status_display())
        remaining_count = max(product.quantity, 1)

        for _ in range(remaining_count):
            group['rows'].append({
                'article': product.article,
                'name': product.name,
                'status_key': product.status,
                'status_label': product.get_status_display(),
                'cost_price': product.cost_price,
                'income': None,
                'profit': None,
                'sale_date': None,
            })
            group['count'] += 1

    sales = SaleRecord.objects.select_related('product').order_by('article', 'sale_date', 'created_at')
    for sale in sales:
        group = get_group(sale.article, 'sold', sale.name, 'Продан')

        group['rows'].append({
            'article': sale.article,
            'name': sale.name,
            'status_key': 'sold',
            'status_label': 'Продан',
            'cost_price': sale_cost_price(sale),
            'income': sale.income,
            'profit': sale.profit,
            'sale_date': sale.sale_date,
        })
        group['count'] += 1
        if sale.income:
            group['total_income'] += sale.income
        if sale.profit:
            group['total_profit'] += sale.profit
        group['has_sales'] = True

    groups = []
    for group in sorted(groups_dict.values(), key=lambda item: (item['sort_status'], item['article'], item['name'])):
        group['header_status_key'] = group['status_key']
        group['header_status_label'] = group['status_label']
        group['header_cost'] = group['rows'][0]['cost_price']
        groups.append(group)

    return render(request, 'web/product_list.html', {'groups': groups})


def export_sales_report(request):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Отчет продаж'
    sheet.append(['Артикул', 'Название', 'Состояние', 'Себестоимость', 'Доход', 'Прибыль', 'Дата продажи'])

    sales = SaleRecord.objects.select_related('product').order_by('sale_date', 'created_at', 'article')
    for sale in sales:
        sheet.append([
            sale.article,
            sale.name,
            'Продан',
            sale_cost_price(sale),
            sale.income,
            sale.profit,
            sale.sale_date,
        ])

    style_export_sheet(sheet, [20, 36, 16, 16, 14, 14, 16])
    return workbook_response(workbook, export_filename('Отчет_продаж'))


def export_stock_balance(request):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Учет остатков'
    sheet.append([
        'Артикул',
        'Название',
        'Стоимость в закупке',
        'Доставка',
        'Себестоимость',
        'На складе',
        'В продаже',
    ])

    products = Product.objects.order_by('article', 'name')
    for product in products:
        in_stock = product.quantity if product.status == 'in_stock' else 0
        in_sale = product.quantity if product.status == 'in_sale' else 0
        sheet.append([
            product.article,
            product.name,
            product.purchase_price,
            product.delivery_cost,
            product.cost_price,
            in_stock,
            in_sale,
        ])

    style_export_sheet(sheet, [20, 36, 20, 14, 16, 14, 14])
    return workbook_response(workbook, export_filename('Учет_остатков'))
