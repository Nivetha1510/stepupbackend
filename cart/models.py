import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from products.models import ProductVariant


class Cart(models.Model):
    """
    A shopping cart. Guests are identified by a random `token` (stored by the
    frontend and sent in the X-Cart-Token header). When a guest logs in, the
    guest cart is merged into the user's cart.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="cart"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart of {self.user}" if self.user else f"Guest cart {str(self.token)[:8]}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]
        constraints = [models.UniqueConstraint(fields=["cart", "variant"], name="unique_cart_variant")]

    def __str__(self):
        return f"{self.quantity} × {self.variant}"

    @property
    def unit_price(self):
        return self.variant.product.selling_price

    @property
    def line_total(self):
        return self.unit_price * self.quantity
