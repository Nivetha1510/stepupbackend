from django.conf import settings
from rest_framework import serializers

from accounts.models import phone_validator, pincode_validator
from .models import Order, OrderItem, OrderStatusHistory


class CheckoutSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=60)
    last_name = serializers.CharField(max_length=60)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15, validators=[phone_validator])
    address_line1 = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=80)
    state = serializers.CharField(max_length=80)
    landmark = serializers.CharField(max_length=120, required=False, allow_blank=True)
    pincode = serializers.CharField(max_length=6, validators=[pincode_validator])
    payment_method = serializers.ChoiceField(choices=Order.PAYMENT_METHOD_CHOICES)
    save_address = serializers.BooleanField(required=False, default=False)


class OrderItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    product_slug = serializers.CharField(source="product.slug", default=None, read_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_slug", "product_name", "brand_name", "size", "color", "image_url",
                  "quantity", "unit_price", "line_total"]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        url = f"{settings.MEDIA_URL}{obj.image}"
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class StatusHistorySerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OrderStatusHistory
        fields = ["status", "label", "note", "created_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    history = StatusHistorySerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_label = serializers.CharField(source="get_payment_method_display", read_only=True)
    payment_status_label = serializers.CharField(source="get_payment_status_display", read_only=True)
    transaction_reference = serializers.CharField(source="payment.transaction_reference", default="", read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "order_number", "status", "status_label", "payment_method", "payment_method_label",
                  "payment_status", "payment_status_label", "transaction_reference", "first_name", "last_name",
                  "email", "phone", "address_line1", "city", "state", "landmark", "pincode", "subtotal",
                  "shipping_cost", "total", "items", "history", "can_cancel", "item_count", "created_at"]

    def get_item_count(self, obj):
        return sum(i.quantity for i in obj.items.all())
