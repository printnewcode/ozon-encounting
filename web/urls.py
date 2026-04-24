from django.urls import path
from . import views

urlpatterns = [
    path('upload/supply/', views.upload_supply, name='upload_supply'),
    path('upload/sales/', views.upload_sales, name='upload_sales'),
    path('products/', views.product_list, name='product_list'),
    path('', views.product_list, name='home'), # Главной страницей сделаем список товаров
]
