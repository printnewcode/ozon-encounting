from django.contrib import admin

from .models import Product, SaleRecord


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('article', 'name', 'quantity', 'cost_price', 'status', 'updated_at')
    list_filter = ('status',)
    search_fields = ('article', 'name')
    readonly_fields = ('cost_price', 'created_at', 'updated_at')


@admin.register(SaleRecord)
class SaleRecordAdmin(admin.ModelAdmin):
    list_display = ('article', 'name', 'sale_type', 'income', 'profit', 'sale_date')
    list_filter = ('sale_type', 'sale_date')
    search_fields = ('article', 'name')
    readonly_fields = ('article', 'name', 'profit', 'created_at')
