from django.urls import path

from . import views

urlpatterns = [
    path("orders/", views.OrderListCreateView.as_view(), name="order-list"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<int:pk>/cancel/", views.OrderCancelView.as_view(), name="order-cancel"),
]
