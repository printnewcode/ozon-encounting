from django.urls import path

from . import views


urlpatterns = [
    path('upload/supply/', views.upload_supply, name='upload_supply'),
    path('upload/sales/', views.upload_sales, name='upload_sales'),
    path('exports/sales-report/', views.export_sales_report, name='export_sales_report'),
    path('exports/stock-balance/', views.export_stock_balance, name='export_stock_balance'),
    path('products/', views.product_list, name='product_list'),
    path('', views.product_list, name='home'),
]
