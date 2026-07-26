from decimal import Decimal
from io import BytesIO

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .admin import IMPORT_PREVIEW_SESSION_KEY
from .models import Product, SaleRecord


class ProductCostImportAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password',
        )
        self.client.force_login(self.user)
        self.target = Product.objects.create(
            article='OZON-ONLY',
            name='Товар только на OZON',
            quantity=0,
            ozon_quantity=5,
            purchase_price=Decimal('0.00'),
            delivery_cost=Decimal('0.00'),
            status='in_sale',
        )
        self.warehouse_product = Product.objects.create(
            article='WAREHOUSE',
            name='Товар на складе',
            quantity=3,
            ozon_quantity=2,
            purchase_price=Decimal('100.00'),
            delivery_cost=Decimal('20.00'),
            status='in_stock_warehouse',
        )
        self.old_sale = SaleRecord.objects.create(
            product=self.target,
            sale_type='ozon',
            income=Decimal('200.00'),
            cost_price=Decimal('0.00'),
        )
        self.import_url = reverse('admin:web_product_import_cost_prices')

    def make_xlsx(self, rows):
        workbook = Workbook()
        worksheet = workbook.active
        for row in rows:
            worksheet.append(row)
        content = BytesIO()
        workbook.save(content)
        return SimpleUploadedFile(
            'cost-prices.xlsx',
            content.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def preview(self):
        upload = self.make_xlsx([
            ['Название товара', 'Себестоимость'],
            ['  Товар   только на OZON  ', '150,50'],
            ['Товар на складе', '999.00'],
            ['Неизвестный товар', '77.00'],
        ])
        return self.client.post(
            self.import_url,
            {'action': 'preview', 'file': upload},
            follow=True,
        )

    def test_product_changelist_has_import_button(self):
        response = self.client.get(reverse('admin:web_product_changelist'))

        self.assertContains(response, 'Импорт себестоимости OZON')
        self.assertContains(response, self.import_url)

    def test_preview_and_apply_updates_only_target_product(self):
        response = self.preview()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Готово к обновлению:')
        self.assertContains(response, '<strong>1</strong>', html=True)
        preview = self.client.session[IMPORT_PREVIEW_SESSION_KEY]
        self.assertEqual(preview['summary']['matched'], 1)
        self.assertEqual(preview['summary']['protected'], 1)
        self.assertEqual(preview['summary']['not_found'], 1)

        response = self.client.post(self.import_url, {'action': 'apply'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.warehouse_product.refresh_from_db()
        self.old_sale.refresh_from_db()
        self.assertEqual(self.target.cost_price, Decimal('150.50'))
        self.assertEqual(self.target.purchase_price, Decimal('150.50'))
        self.assertEqual(self.target.delivery_cost, Decimal('0.00'))
        self.assertEqual(self.warehouse_product.cost_price, Decimal('120.00'))
        self.assertEqual(self.old_sale.cost_price, Decimal('0.00'))
        self.assertNotIn(IMPORT_PREVIEW_SESSION_KEY, self.client.session)
        self.assertTrue(
            LogEntry.objects.filter(
                user=self.user,
                object_id=str(self.target.id),
                change_message__contains='cost-prices.xlsx',
            ).exists()
        )

    def test_apply_stops_if_product_changed_after_preview(self):
        self.preview()
        self.target.purchase_price = Decimal('10.00')
        self.target.save()

        response = self.client.post(self.import_url, {'action': 'apply'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.cost_price, Decimal('10.00'))
        self.assertContains(response, 'изменился после предпросмотра')
        self.assertIn(IMPORT_PREVIEW_SESSION_KEY, self.client.session)

    def test_duplicate_names_in_file_are_not_applied(self):
        upload = self.make_xlsx([
            ['Товар только на OZON', '150.00'],
            ['Товар только на OZON', '160.00'],
        ])

        self.client.post(
            self.import_url,
            {'action': 'preview', 'file': upload},
            follow=True,
        )

        preview = self.client.session[IMPORT_PREVIEW_SESSION_KEY]
        self.assertEqual(preview['summary']['matched'], 0)
        self.assertEqual(preview['summary']['duplicate'], 2)
