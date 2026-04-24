import pandas as pd
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Product, SaleRecord
from .forms import SupplyUploadForm, SalesUploadForm

def parse_file(file):
    """ Вспомогательная функция для парсинга Excel/CSV файлов через pandas. """
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    
    # Очищаем колонки от лишних пробелов для надежности
    df.columns = df.columns.str.strip()
    return df

def upload_supply(request):
    if request.method == 'POST':
        form = SupplyUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            try:
                df = parse_file(file)
                # Ожидаемые колонки по задаче (либо их английские аналоги, если потребуется)
                # Для стабильности мы постараемся искать по индексам или конкретным названиям
                # Согласно примеру: Article | Name | Purchase Cost | Delivery | Cost Price | Quantity
                # Мы возьмем нужные поля:
                
                products_created = 0
                for index, row in df.iterrows():
                    # Безопасное извлечение с учетом возможных разных именований столбцов
                    article = str(row.iloc[0]).strip()
                    name = str(row.iloc[1]).strip()
                    purchase_price = row.iloc[2]
                    delivery_cost = row.iloc[3]
                    # Извлекаем количество (6 столбец, индекс 5)
                    quantity = int(row.iloc[5]) if len(row.columns) > 5 else int(row.get('Количество', 0))

                    # Создаем товар или обновляем, если он уже был
                    product, created = Product.objects.update_or_create(
                        article=article,
                        defaults={
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
                    income = row.iloc[2]
                    # Извлекаем количество
                    quantity_sold = int(row.iloc[3]) if len(row.columns) > 3 else 1

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
    products = Product.objects.all().order_by('-created_at')
    return render(request, 'web/product_list.html', {'products': products})
