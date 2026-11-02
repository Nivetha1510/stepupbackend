from django.conf import settings
from django.db import models

from products.models import Product, ProductVariant


class Order(models.Model):
    STATUS_PLACED = "placed"
    STATUS_PROCESSING = "processing"
    STATUS_DISPATCHED = "dispatched"
    STATUS_IN_TRANSIT = "in_transit"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PLACED, "Order Placed"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DISPATCHED, "Order Dispatched"),
        (STATUS_IN_TRANSIT, "Order in transit"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_FAILED = "failed"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_FAILED, "Failed"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]

    METHOD_COD = "cod"
    METHOD_DEMO = "demo_online"
    METHOD_RAZORPAY = "razorpay"
    METHOD_UPI = "upi"
    PAYMENT_METHOD_CHOICES = [
        (METHOD_COD, "Cash on Delivery"),
        (METHOD_DEMO, "Online payment (demo)"),
        (METHOD_RAZORPAY, "Online payment (Razorpay)"),
        (METHOD_UPI, "UPI"),
    ]

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLACED, db_index=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_PENDING)

    # Customer + shipping snapshot (copied at purchase time so later profile edits don't change history)
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    address_line1 = models.CharField(max_length=255)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    landmark = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=6)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    idempotency_key = models.CharField(max_length=64, blank=True, null=True, unique=True,
                                       help_text="Prevents duplicate submissions of the same checkout")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.order_number}"

    @property
    def can_cancel(self):
        return self.status in (self.STATUS_PLACED, self.STATUS_PROCESSING)

    def save(self, *args, **kwargs):
        creating = self._state.adding
        previous_status = None
        if not creating:
            previous_status = Order.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        if not self.order_number:
            # Temporary unique value; replaced with a friendly number once we have a PK.
            import uuid
            self.order_number = uuid.uuid4().hex[:20]
        super().save(*args, **kwargs)
        if creating:
            self.order_number = f"SU{2300000 + self.pk}"
            Order.objects.filter(pk=self.pk).update(order_number=self.order_number)
        if creating or previous_status != self.status:
            OrderStatusHistory.objects.create(order=self, status=self.status)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name="order_items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, related_name="order_items")
    product_name = models.CharField(max_length=160)
    brand_name = models.CharField(max_length=80, blank=True)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=40)
    image = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} × {self.product_name} ({self.color}/{self.size})"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class OrderStatusHistory(models.Model):
    """Timeline entries shown on the Track Order page."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES)
    note = models.CharField(max_length=200, blank=True, help_text="e.g. 'Reached at Tenkasi Post office'")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "order status history"

    def __str__(self):
        return f"{self.order} → {self.get_status_display()}"
