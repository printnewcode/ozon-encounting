from django.db import models
from django.utils import timezone


class Product(models.Model):
    STATUS_CHOICES = (
        ('in_stock', 'В наличии'),
        ('in_sale', 'В продаже'),
        ('sold', 'Продано'),
    )

    article = models.CharField(max_length=100, unique=True, verbose_name='Артикул/SKU')
    name = models.CharField(max_length=255, verbose_name='Название товара')
    quantity = models.IntegerField(default=0, verbose_name='Количество на складе')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Закупочная стоимость')
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Стоимость доставки')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Себестоимость')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_stock', verbose_name='Статус')
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
    article = models.CharField(max_length=100, verbose_name='Артикул/SKU')
    name = models.CharField(max_length=255, verbose_name='Название')
    sale_type = models.CharField(max_length=20, choices=SALE_TYPE_CHOICES, verbose_name='Тип продажи')
    income = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Доход (цена продажи)')
    profit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='Прибыль')
    sale_date = models.DateField(default=timezone.localdate, verbose_name='Дата продажи')
    external_id = models.CharField(max_length=255, blank=True, null=True, unique=True, verbose_name='Внешний ID')
    posting_number = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name='Ozon posting number')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания записи')

    def save(self, *args, **kwargs) -> None:
        if self.product:
            self.article = self.product.article
            self.name = self.product.name
            if self.income is not None and self.product.cost_price is not None:
                self.profit = self.income - self.product.cost_price
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'Продажа {self.article} - {self.sale_date}'

    class Meta:
        verbose_name = 'Запись о продаже'
        verbose_name_plural = 'Записи о продажах'
