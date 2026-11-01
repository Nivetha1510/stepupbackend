from django.urls import path

from . import views

urlpatterns = [
    path("payments/config/", views.PaymentConfigView.as_view(), name="payment-config"),
    path("payments/start/", views.StartPaymentView.as_view(), name="payment-start"),
    path("payments/verify/", views.VerifyPaymentView.as_view(), name="payment-verify"),
    path("payments/webhook/", views.RazorpayWebhookView.as_view(), name="payment-webhook"),
]
