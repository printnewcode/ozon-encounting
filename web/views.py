import io
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db.models import F
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Product, SaleRecord
from .forms import SupplyUploadForm, SalesUploadForm

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
    rows = []

    # --- Товары, которые ещё не проданы (в наличии или в продаже) ---
    unsold = Product.objects.filter(status__in=['in_stock', 'in_sale']).order_by('created_at')
    for p in unsold:
        rows.append({
            'article':      p.article,
            'name':         p.name,
            'status_key':   p.status,
            'status_label': p.get_status_display(),
            'cost_price':   p.cost_price,
            'income':       None,
            'profit':       None,
            'sale_date':    None,
        })

    # --- Записи о продажах (каждая продажа — отдельная строка) ---
    sales = SaleRecord.objects.select_related('product').order_by('sale_date', 'created_at')
    for s in sales:
        rows.append({
            'article':      s.article,
            'name':         s.name,
            'status_key':   'sold',
            'status_label': 'Продан',
            'cost_price':   s.product.cost_price,
            'income':       s.income,
            'profit':       s.profit,
            'sale_date':    s.sale_date,
        })

    # --- Добавляем метки групп для визуального разделения ---
    current_article = None
    group_idx = 0
    for row in rows:
        if row['article'] != current_article:
            current_article = row['article']
            group_idx = 1 - group_idx   # переключаем 0 <-> 1
            row['is_group_start'] = True
        else:
            row['is_group_start'] = False
        row['group_idx'] = group_idx

    return render(request, 'web/product_list.html', {'rows': rows})

