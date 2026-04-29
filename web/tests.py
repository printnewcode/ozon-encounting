from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from .models import Product, SaleRecord
from .views import parse_file


class ProductModelTests(TestCase):
    def test_save_calculates_cost_price(self):
        product = Product.objects.create(
            article='SKU-1',
            name='Тестовый товар',
            quantity=2,
            purchase_price=Decimal('100.50'),
            delivery_cost=Decimal('20.25'),
        )

        self.assertEqual(product.cost_price, Decimal('120.75'))


class SaleUploadTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            article='SKU-1',
            name='Тестовый товар',
            quantity=3,
            purchase_price=Decimal('100.00'),
            delivery_cost=Decimal('25.00'),
        )

    def test_sales_upload_creates_records_and_decreases_stock(self):
        upload = SimpleUploadedFile(
            'sales.csv',
            'Артикул;Название;Доход;Количество\nSKU-1;Тестовый товар;200,50;2\n'.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('upload_sales'),
            {'sale_type': 'ozon', 'file': upload},
        )

        self.assertRedirects(response, reverse('product_list'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 1)
        self.assertEqual(self.product.status, 'in_sale')
        self.assertEqual(SaleRecord.objects.count(), 2)
        self.assertEqual(SaleRecord.objects.first().profit, Decimal('75.50'))

    def test_negative_sales_quantity_is_rejected_without_stock_change(self):
        upload = SimpleUploadedFile(
            'sales.csv',
            'Артикул;Название;Доход;Количество\nSKU-1;Тестовый товар;200;-1\n'.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('upload_sales'),
            {'sale_type': 'ozon', 'file': upload},
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 3)
        self.assertEqual(SaleRecord.objects.count(), 0)

    def test_free_sale_does_not_move_remaining_product_to_in_sale(self):
        upload = SimpleUploadedFile(
            'sales.csv',
            'Артикул;Название;Доход;Количество\nSKU-1;Тестовый товар;200;1\n'.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('upload_sales'),
            {'sale_type': 'free', 'file': upload},
        )

        self.assertRedirects(response, reverse('product_list'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 2)
        self.assertEqual(self.product.status, 'in_stock')

    def test_sales_upload_warns_about_name_mismatch_and_oversell(self):
        upload = SimpleUploadedFile(
            'sales.csv',
            'Артикул;Название;Доход;Количество\nSKU-1;Другое имя;200;5\n'.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('upload_sales'),
            {'sale_type': 'free', 'file': upload},
            follow=True,
        )

        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(any('название в файле отличается от базы' in message for message in messages))
        self.assertTrue(any('остаток обнулен' in message for message in messages))
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, 'sold')


class SupplyUploadTests(TestCase):
    def test_supply_upload_creates_product_from_csv(self):
        upload = SimpleUploadedFile(
            'supply.CSV',
            'Артикул;Название;Закупка;Доставка;Себестоимость;Количество\nSKU-2;Новый товар;50;10;60;4\n'.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(reverse('upload_supply'), {'file': upload})

        self.assertRedirects(response, reverse('product_list'))
        product = Product.objects.get(article='SKU-2')
        self.assertEqual(product.quantity, 4)
        self.assertEqual(product.cost_price, Decimal('60.00'))


class ExportTests(TestCase):
    def test_sales_report_uses_sale_time_cost_price(self):
        product = Product.objects.create(
            article='SKU-1',
            name='Тестовый товар',
            quantity=1,
            purchase_price=Decimal('100.00'),
            delivery_cost=Decimal('25.00'),
        )
        SaleRecord.objects.create(product=product, sale_type='free', income=Decimal('200.00'))
        product.purchase_price = Decimal('300.00')
        product.delivery_cost = Decimal('50.00')
        product.save()

        response = self.client.get(reverse('export_sales_report'))
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook.active

        self.assertEqual(sheet['D2'].value, 125)
        self.assertEqual(sheet['F2'].value, 75)


class ParseFileTests(TestCase):
    def test_parse_file_supports_cp1251_csv(self):
        upload = SimpleUploadedFile(
            'sales.csv',
            'Артикул;Название;Доход\nSKU-1;Товар;100\n'.encode('cp1251'),
            content_type='text/csv',
        )

        df = parse_file(upload)

        self.assertEqual(list(df.columns), ['Артикул', 'Название', 'Доход'])
        self.assertEqual(df.iloc[0]['Название'], 'Товар')
