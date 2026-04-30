from django.contrib import admin

from .models import Product, SaleRecord


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('article', 'name', 'quantity', 'cost_price', 'status', 'ozon_visibility', 'ozon_status', 'updated_at')
    list_filter = ('status', 'ozon_visibility', 'ozon_status')
    search_fields = ('article', 'name', 'ozon_product_id', 'ozon_sku', 'ozon_visibility', 'ozon_status')
    readonly_fields = ('cost_price', 'created_at', 'updated_at')


@admin.register(SaleRecord)
class SaleRecordAdmin(admin.ModelAdmin):
    list_display = ('article', 'name', 'sale_type', 'income', 'profit', 'sale_date', 'posting_number')
    list_filter = ('sale_type', 'sale_date')
    search_fields = ('article', 'name', 'external_id', 'posting_number')
    readonly_fields = ('article', 'name', 'profit', 'created_at')
