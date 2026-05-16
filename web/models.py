from django.db import models
from django.utils import timezone


class Product(models.Model):
    STATUS_CHOICES = (
        ('in_stock_warehouse', 'В наличии/Склад'),
        ('in_stock_ozon', 'В наличии/OZON'),
        ('in_sale', 'В продаже'),
        ('sold', 'Продано'),
    )

    article = models.CharField(max_length=100, unique=True, verbose_name='Артикул/SKU')
    name = models.CharField(max_length=255, verbose_name='Название товара')
    quantity = models.IntegerField(default=0, verbose_name='Количество на складе')
    ozon_quantity = models.IntegerField(default=0, verbose_name='Количество на OZON')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Закупочная стоимость')
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Стоимость доставки')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Себестоимость')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='in_stock_warehouse', verbose_name='Статус')
    ozon_product_id = models.BigIntegerField(blank=True, null=True, db_index=True, verbose_name='Ozon product ID')
    ozon_sku = models.BigIntegerField(blank=True, null=True, db_index=True, verbose_name='Ozon SKU')
    ozon_visibility = models.CharField(max_length=50, blank=True, verbose_name='Ozon visibility')
    ozon_status = models.CharField(max_length=100, blank=True, verbose_name='Ozon status')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания записи')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления записи')

    def save(self, *args, **kwargs) -> None:
        if self.purchase_price is not None and self.delivery_cost is not None:
            self.cost_price = self.purchase_price + self.delivery_cost
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.article} - {self.name}'

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'


class SupplyBatch(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='batches',
        verbose_name='РўРѕРІР°СЂ',
    )
    initial_quantity = models.IntegerField(default=0, verbose_name='РљРѕР»РёС‡РµСЃС‚РІРѕ РІ РїР°СЂС‚РёРё')
    remaining_quantity = models.IntegerField(default=0, verbose_name='РћСЃС‚Р°С‚РѕРє РїР°СЂС‚РёРё')
    cost_remaining_quantity = models.IntegerField(default=0, verbose_name='Остаток для расчета себестоимости')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Р—Р°РєСѓРїРѕС‡РЅР°СЏ СЃС‚РѕРёРјРѕСЃС‚СЊ')
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='РЎС‚РѕРёРјРѕСЃС‚СЊ РґРѕСЃС‚Р°РІРєРё')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='РЎРµР±РµСЃС‚РѕРёРјРѕСЃС‚СЊ')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Р”Р°С‚Р° РїРѕСЃС‚Р°РІРєРё')

    def save(self, *args, **kwargs) -> None:
        if self.purchase_price is not None and self.delivery_cost is not None:
            self.cost_price = self.purchase_price + self.delivery_cost
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.product.article} - {self.remaining_quantity}/{self.initial_quantity}'

    class Meta:
        ordering = ('created_at', 'id')
        verbose_name = 'РџР°СЂС‚РёСЏ РїРѕСЃС‚Р°РІРєРё'
        verbose_name_plural = 'РџР°СЂС‚РёРё РїРѕСЃС‚Р°РІРѕРє'


class SaleRecord(models.Model):
    SALE_TYPE_CHOICES = (
        ('ozon', 'Продажа Ozon'),
        ('free', 'Свободная продажа'),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='sales',
        verbose_name='Связанный товар',
    )
    supply_batch = models.ForeignKey(
        SupplyBatch,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sales',
        verbose_name='Партия поставки',
    )
    article = models.CharField(max_length=100, verbose_name='Артикул/SKU')
    name = models.CharField(max_length=255, verbose_name='Название')
    sale_type = models.CharField(max_length=20, choices=SALE_TYPE_CHOICES, verbose_name='Тип продажи')
    income = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Доход (цена продажи)')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='Себестоимость на момент продажи')
    profit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='Прибыль')
    sale_date = models.DateField(default=timezone.localdate, verbose_name='Дата продажи')
    accrual_date = models.DateField(blank=True, null=True, verbose_name='Дата начисления')
    accrual_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name='Ozon accrual ID')
    accrual_details = models.JSONField(blank=True, default=dict, verbose_name='Ozon accrual details')
    external_id = models.CharField(max_length=255, blank=True, null=True, unique=True, verbose_name='Внешний ID')
    posting_number = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name='Ozon posting number')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания записи')

    def save(self, *args, **kwargs) -> None:
        if self.product:
            self.article = self.product.article
            self.name = self.product.name
            if self.cost_price is None:
                if self.supply_batch_id and self.supply_batch and self.supply_batch.cost_price is not None:
                    self.cost_price = self.supply_batch.cost_price
                elif self.product.cost_price is not None:
                    self.cost_price = self.product.cost_price
            if self.income is not None and self.cost_price is not None:
                self.profit = self.income - self.cost_price
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'Продажа {self.article} - {self.sale_date}'

    class Meta:
        verbose_name = 'Запись о продаже'
        verbose_name_plural = 'Записи о продажах'
