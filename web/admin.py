from django.contrib import admin

from .models import Product, SaleRecord, SupplyBatch


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('article', 'name', 'quantity', 'cost_price', 'status', 'ozon_visibility', 'ozon_status', 'updated_at')
    list_filter = ('status', 'ozon_visibility', 'ozon_status')
    search_fields = ('article', 'name', 'ozon_product_id', 'ozon_sku', 'ozon_visibility', 'ozon_status')
    readonly_fields = ('cost_price', 'created_at', 'updated_at')


@admin.register(SupplyBatch)
class SupplyBatchAdmin(admin.ModelAdmin):
    list_display = ('product', 'initial_quantity', 'remaining_quantity', 'cost_remaining_quantity', 'cost_price', 'created_at')
    search_fields = ('product__article', 'product__name')
    readonly_fields = ('cost_price', 'created_at')


@admin.register(SaleRecord)
class SaleRecordAdmin(admin.ModelAdmin):
    list_display = ('article', 'name', 'sale_type', 'income', 'cost_price', 'profit', 'sale_date', 'posting_number')
    list_filter = ('sale_type', 'sale_date')
    search_fields = ('article', 'name', 'external_id', 'posting_number')
    readonly_fields = ('article', 'name', 'profit', 'created_at')
