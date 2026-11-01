from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Order, OrderItem, OrderStatusHistory
from .services import restock_order


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ["preview", "product_name", "brand_name", "color", "size", "quantity", "unit_price", "line_total"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="")
    def preview(self, obj):
        if not obj.image:
            return "—"
        return format_html('<img src="/media/{}" style="height:48px;width:48px;object-fit:contain;'
                           'background:#eee;border-radius:6px" />', obj.image)

    @admin.display(description="Line total (₹)")
    def line_total(self, obj):
        return obj.line_total


class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ["status", "note", "created_at"]
    readonly_fields = ["status", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "customer", "created_at", "total", "payment_method", "payment_status",
                    "status_badge", "status"]
    list_editable = ["status"]
    list_filter = ["status", "payment_status", "payment_method", "created_at"]
    search_fields = ["order_number", "email", "first_name", "last_name", "phone", "user__email"]
    inlines = [OrderItemInline, StatusHistoryInline]
    readonly_fields = ["order_number", "user", "subtotal", "shipping_cost", "total", "payment_method",
                       "idempotency_key", "created_at", "updated_at"]
    fieldsets = [
        ("Order", {"fields": ["order_number", "user", "status", "created_at", "updated_at"]}),
        ("Payment", {"fields": ["payment_method", "payment_status", "subtotal", "shipping_cost", "total"]}),
        ("Customer", {"fields": ["first_name", "last_name", "email", "phone"]}),
        ("Shipping address", {"fields": ["address_line1", "landmark", "city", "state", "pincode"]}),
        ("Technical", {"fields": ["idempotency_key"], "classes": ["collapse"]}),
    ]
    actions = ["mark_dispatched", "mark_in_transit", "mark_delivered"]

    @admin.display(description="Customer")
    def customer(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email

    @admin.display(description="Progress")
    def status_badge(self, obj):
        colours = {"placed": "#2F4F4F", "processing": "#5f7f7f", "dispatched": "#3c6e71",
                   "in_transit": "#c77700", "delivered": "#2e7d32", "cancelled": "#b00020"}
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px">{}</span>',
                           colours.get(obj.status, "#555"), obj.get_status_display())

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            previous = Order.objects.get(pk=obj.pk).status
            if obj.status == Order.STATUS_CANCELLED and previous != Order.STATUS_CANCELLED:
                restock_order(obj)
                messages.info(request, "Order cancelled — items were returned to stock.")
            if obj.status == Order.STATUS_DELIVERED and obj.payment_method == Order.METHOD_COD:
                obj.payment_status = Order.PAYMENT_PAID
        super().save_model(request, obj, form, change)
        if hasattr(obj, "payment"):
            obj.payment.status = obj.payment_status
            obj.payment.save(update_fields=["status", "updated_at"])

    def _bulk_status(self, request, queryset, status):
        for order in queryset.exclude(status=Order.STATUS_CANCELLED):
            order.status = status
            if status == Order.STATUS_DELIVERED and order.payment_method == Order.METHOD_COD:
                order.payment_status = Order.PAYMENT_PAID
            order.save()
        self.message_user(request, f"Updated {queryset.count()} order(s).")

    @admin.action(description="Mark as dispatched")
    def mark_dispatched(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_DISPATCHED)

    @admin.action(description="Mark as in transit")
    def mark_in_transit(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_IN_TRANSIT)

    @admin.action(description="Mark as delivered")
    def mark_delivered(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_DELIVERED)
