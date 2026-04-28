import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import pandas as pd
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from .models import Product, SaleRecord
from .forms import SupplyUploadForm, SalesUploadForm


def export_filename(name):
    timestamp = datetime.now().strftime('%Y-%m-%d')
    return f'{name}_{timestamp}.xlsx'


def workbook_response(workbook, filename):
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


def style_export_sheet(sheet, widths):
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
            if header in ('Стоимость в закупке', 'Доставка', 'Себестоимость', 'Доход', 'Прибыль'):
                cell.number_format = '#,##0.00'
            elif header == 'Дата продажи':
                cell.number_format = 'DD.MM.YYYY'

def parse_file(file):
    """ Вспомогательная функция для парсинга Excel/CSV файлов через pandas. """
    if file.name.endswith('.csv'):
        # Читаем содержимое файла в память
        content = file.read()
        
        # Пробуем разные кодировки
        for encoding in ['utf-8', 'cp1251']:
            try:
                # Превращаем байты в текст и оборачиваем в StringIO для pandas
                decoded_content = content.decode(encoding)
                separator = ';' if ';' in decoded_content else ','
                
                df = pd.read_csv(io.StringIO(decoded_content), sep=separator)
                break # Если прочитали успешно — выходим из цикла
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Не удалось определить кодировку файла. Используйте UTF-8 или CP1251.")
    else:
        df = pd.read_excel(file)
    
    # Очищаем колонки от лишних пробелов для надежности
    df.columns = df.columns.str.strip()
    # Заменяем все пустые ячейки (NaN) на 0 или пустую строку
    df = df.fillna(0) 
    return df

def upload_supply(request):
    if request.method == 'POST':
        form = SupplyUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            try:
                df = parse_file(file)
                
                products_created = 0
                for index, row in df.iterrows():
                    # Извлегчение столбцов
                    # Артикул
                    article = str(row.iloc[0]).strip()
                    if article.lower() == "артикул" or article.lower() == "article" or not article or article == "nan":
                        continue
                    # Название
                    name = str(row.iloc[1]).strip()
                    # Стоимость закупки
                    purchase_price = row.iloc[2]
                    # Стоимость доставки
                    delivery_cost = row.iloc[3]
                    # Количество
                    quantity = int(row.iloc[5]) if df.shape[1] > 5 else int(row.get('Количество', 0))

                    # Создаем товар или обновляем, если он уже был
                    product, created = Product.objects.update_or_create(
                        article=article,
                        defaults={
                            'purchase_price': purchase_price,
                            'delivery_cost': delivery_cost,
                            'quantity': F('quantity') + quantity,
                            'status': 'in_stock', 
                        },
                        create_defaults={
                            'name': name,
                            'purchase_price': purchase_price,
                            'delivery_cost': delivery_cost,
                            'quantity': quantity,
                            'status': 'in_stock'
                        }
                    )
                    products_created += 1

                messages.success(request, f'Успешно загружено {products_created} товаров из поставки.')
                return redirect('product_list')
            except Exception as e:
                messages.error(request, f'Ошибка при обработке файла: {e}')
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
                # Формат: Article | Name | Income | Quantity
                
                sales_created = 0
                errors = []
                for index, row in df.iterrows():
                    article = str(row.iloc[0]).strip()
                    name = str(row.iloc[1]).strip()
                    # Явное приведение к Decimal, чтобы не было конфликта типов str vs Decimal
                    try:
                        income = Decimal(str(row.iloc[2]).strip().replace(',', '.'))
                    except InvalidOperation:
                        errors.append(f"Строка {index+1}: некорректное значение дохода '{row.iloc[2]}'")
                        continue
                    # Извлекаем количество (df.shape[1] = число колонок DataFrame, не Series)
                    quantity_sold = int(row.iloc[3]) if df.shape[1] > 3 else 1

                    try:
                        product = Product.objects.get(article=article)
                        
                        # Обновляем статус и количество товара
                        product.quantity -= quantity_sold
                        if product.quantity <= 0:
                            product.status = 'sold'
                            product.quantity = 0
                        else:
                            product.status = 'in_sale'
                        product.save()

                        # Создаем запись о продаже
                        # Прибыль рассчитается автоматически в методе save()
                        for _ in range(quantity_sold):
                            SaleRecord.objects.create(
                                product=product,
                                sale_type=sale_type,
                                income=income,
                                # Название и артикул скопируются автоматически
                            )
                        sales_created += quantity_sold

                    except Product.DoesNotExist:
                        errors.append(f"Товар с артикулом {article} не найден в базе.")
                
                if sales_created > 0:
                    messages.success(request, f'Успешно загружено {sales_created} записей о продажах.')
                if errors:
                    messages.warning(request, "Некоторые товары не были найдены: " + ", ".join(errors[:5]) + ("..." if len(errors)>5 else ""))
                
                return redirect('product_list')
            except Exception as e:
                messages.error(request, f'Ошибка при обработке файла: {e}')
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

    # --- 1. Fetch Unsold Products ---
    unsold = Product.objects.filter(status__in=['in_stock', 'in_sale']).order_by('article', 'created_at')
    for p in unsold:
        group = get_group(p.article, p.status, p.name, p.get_status_display())
        remaining_count = max(p.quantity, 1)

        for _ in range(remaining_count):
            group['rows'].append({
                'article':      p.article,
                'name':         p.name,
                'status_key':   p.status,
                'status_label': p.get_status_display(),
                'cost_price':   p.cost_price,
                'income':       None,
                'profit':       None,
                'sale_date':    None,
            })
            group['count'] += 1

    # --- 2. Fetch Sale Records ---
    sales = SaleRecord.objects.select_related('product').order_by('article', 'sale_date', 'created_at')
    for s in sales:
        group = get_group(s.article, 'sold', s.name, 'Продан')

        group['rows'].append({
            'article':      s.article,
            'name':         s.name,
            'status_key':   'sold',
            'status_label': 'Продан',
            'cost_price':   s.product.cost_price,
            'income':       s.income,
            'profit':       s.profit,
            'sale_date':    s.sale_date,
        })
        group['count'] += 1
        if s.income:
            group['total_income'] += s.income
        if s.profit:
            group['total_profit'] += s.profit
        group['has_sales'] = True

    # --- 3. Finalize Groups ---
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
            sale.product.cost_price,
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

