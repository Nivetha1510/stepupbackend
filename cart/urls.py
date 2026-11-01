from django.urls import path

from . import views

urlpatterns = [
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/items/", views.CartItemCreateView.as_view(), name="cart-item-add"),
    path("cart/items/<int:pk>/", views.CartItemDetailView.as_view(), name="cart-item-detail"),
]
