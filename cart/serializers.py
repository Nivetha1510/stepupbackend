from django.conf import settings
from rest_framework import serializers

from products.models import Product, ProductVariant
from .models import CartItem
from .services import cart_totals


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="variant.product.id", read_only=True)
    product_slug = serializers.CharField(source="variant.product.slug", read_only=True)
    name = serializers.CharField(source="variant.product.name", read_only=True)
    brand = serializers.CharField(source="variant.product.brand.name", default=None, read_only=True)
    image = serializers.ImageField(source="variant.product.image", read_only=True)
    size = serializers.CharField(source="variant.size", read_only=True)
    color = serializers.CharField(source="variant.color.name", read_only=True)
    color_hex = serializers.CharField(source="variant.color.hex_code", read_only=True)
    stock = serializers.IntegerField(source="variant.stock", read_only=True)
    price = serializers.DecimalField(source="variant.product.price", max_digits=10, decimal_places=2, read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    available_sizes = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "variant", "product_id", "product_slug", "name", "brand", "image", "size", "color",
                  "color_hex", "stock", "price", "unit_price", "quantity", "line_total", "available_sizes",
                  "is_available"]

    def get_available_sizes(self, obj):
        """Other in-stock sizes in the same colour, so the cart's Size dropdown can switch variants."""
        siblings = ProductVariant.objects.filter(product_id=obj.variant.product_id, color_id=obj.variant.color_id)
        return [{"variant": v.id, "size": v.size, "stock": v.stock} for v in siblings]

    def get_is_available(self, obj):
        product = obj.variant.product
        return product.status == Product.STATUS_ACTIVE and obj.variant.stock >= obj.quantity


def serialize_cart(cart, request=None):
    if cart is None:
        return {"token": None, "items": [], "count": 0, "subtotal": "0.00", "shipping": "0.00", "total": "0.00",
                "free_shipping_threshold": settings.FREE_SHIPPING_THRESHOLD}
    items = list(cart.items.select_related("variant__product__brand", "variant__color"))
    subtotal, shipping, total = cart_totals(items)
    return {
        "token": str(cart.token) if cart.user_id is None else None,
        "items": CartItemSerializer(items, many=True, context={"request": request}).data,
        "count": sum(i.quantity for i in items),
        "subtotal": f"{subtotal:.2f}",
        "shipping": f"{shipping:.2f}",
        "total": f"{total:.2f}",
        "free_shipping_threshold": settings.FREE_SHIPPING_THRESHOLD,
    }


class AddItemSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product").filter(product__status=Product.STATUS_ACTIVE)
    )
    quantity = serializers.IntegerField(min_value=1, max_value=settings.MAX_ITEM_QUANTITY, default=1)


class UpdateItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=settings.MAX_ITEM_QUANTITY, required=False)
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all(), required=False)
