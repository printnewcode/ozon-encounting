from django.urls import path

from . import views


urlpatterns = [
    path('upload/supply/', views.upload_supply, name='upload_supply'),
    path('upload/sales/', views.upload_sales, name='upload_sales'),
    path('sync/ozon/', views.sync_ozon, name='sync_ozon'),
    path('products/cost-price/update/', views.update_cost_price, name='update_cost_price'),
    path('products/cost-price/undo/', views.undo_cost_price, name='undo_cost_price'),
    path('statistics/', views.sales_statistics, name='sales_statistics'),
    path('reports/sales/', views.sales_report_period, name='sales_report_period'),
    path('exports/sales-report/', views.export_sales_report, name='export_sales_report'),
    path('exports/stock-balance/', views.export_stock_balance, name='export_stock_balance'),
    path('products/', views.product_list, name='product_list'),
    path('', views.product_list, name='home'),
]
