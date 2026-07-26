from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .forms import CostPriceImportForm
from .models import Product, SaleRecord, SupplyBatch
from .services.cost_price_import import (
    CostPriceImportError,
    apply_cost_price_import,
    build_import_preview,
)

IMPORT_PREVIEW_SESSION_KEY = 'ozon_cost_price_import_preview'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('article', 'name', 'quantity', 'cost_price', 'status', 'ozon_visibility', 'ozon_status', 'updated_at')
    list_filter = ('status', 'ozon_visibility', 'ozon_status')
    search_fields = ('article', 'name', 'ozon_product_id', 'ozon_sku', 'ozon_visibility', 'ozon_status')
    readonly_fields = ('cost_price', 'created_at', 'updated_at')
    change_list_template = 'admin/web/product/change_list.html'

    def get_urls(self):
        custom_urls = [
            path(
                'import-cost-prices/',
                self.admin_site.admin_view(self.import_cost_prices_view),
                name='web_product_import_cost_prices',
            ),
        ]
        return custom_urls + super().get_urls()

    def import_cost_prices_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        cost_import = request.session.get(IMPORT_PREVIEW_SESSION_KEY) if request.GET.get('preview') else None
        form = CostPriceImportForm()
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'preview':
                form = CostPriceImportForm(request.POST, request.FILES)
                if form.is_valid():
                    try:
                        cost_import = build_import_preview(form.cleaned_data['file'])
                    except CostPriceImportError as exc:
                        self.message_user(request, str(exc), level=messages.ERROR)
                    else:
                        request.session[IMPORT_PREVIEW_SESSION_KEY] = cost_import
                        return redirect(f'{request.path}?preview=1')
            elif action == 'apply':
                cost_import = request.session.get(IMPORT_PREVIEW_SESSION_KEY)
                if not cost_import:
                    self.message_user(
                        request,
                        'Предпросмотр не найден. Загрузите файл заново.',
                        level=messages.ERROR,
                    )
                    return redirect(request.path)
                try:
                    with transaction.atomic():
                        updates = apply_cost_price_import(
                            cost_import,
                            apply_to_past_sales=request.POST.get('apply_to_past_sales') == '1',
                        )
                        for update in updates:
                            product = update['product']
                            row = update['row']
                            changes = []
                            if update['product_updated']:
                                changes.append(
                                    f'себестоимость товара {row["old_cost_price"]} → {row["cost_price"]}'
                                )
                            if update['sales_updated']:
                                changes.append(
                                    f'обновлено прошлых продаж OZON: {update["sales_updated"]}'
                                )
                            self.log_change(
                                request,
                                product,
                                (
                                    f'Импорт себестоимости OZON из файла «{cost_import["file_name"]}»: '
                                    f'{", ".join(changes)}.'
                                ),
                            )
                except CostPriceImportError as exc:
                    self.message_user(request, str(exc), level=messages.ERROR)
                else:
                    products_updated = sum(update['product_updated'] for update in updates)
                    sales_updated = sum(update['sales_updated'] for update in updates)
                    del request.session[IMPORT_PREVIEW_SESSION_KEY]
                    self.message_user(
                        request,
                        (
                            f'Обновлено карточек товаров: {products_updated}; '
                            f'прошлых продаж OZON: {sales_updated}.'
                        ),
                        level=messages.SUCCESS,
                    )
                    return redirect(reverse('admin:web_product_changelist'))

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Импорт себестоимости товаров OZON',
            'form': form,
            'cost_import': cost_import,
        }
        return TemplateResponse(request, 'admin/web/product/import_cost_prices.html', context)


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
