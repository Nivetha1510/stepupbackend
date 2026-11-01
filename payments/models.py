from django.db import models

from orders.models import Order


class Payment(models.Model):
    """
    Payment record for an order.

    Cash on Delivery, a *demo* online payment, and Razorpay are supported. No
    card numbers, CVVs or other card data are ever sent to or stored by this
    backend: Razorpay's hosted checkout collects them, and an order is only
    marked paid after its signature is verified server-side.
    """

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    method = models.CharField(max_length=20, choices=Order.PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=Order.PAYMENT_STATUS_CHOICES, default=Order.PAYMENT_PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_reference = models.CharField(max_length=64, blank=True)
    gateway_order_id = models.CharField(max_length=64, blank=True, help_text="Razorpay order id")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_method_display()} for {self.order} — {self.get_status_display()}"
