from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["order", "method", "status", "amount", "transaction_reference", "created_at"]
    list_filter = ["method", "status"]
    search_fields = ["order__order_number", "transaction_reference", "gateway_order_id"]
    readonly_fields = ["order", "method", "amount", "transaction_reference", "gateway_order_id", "created_at", "updated_at"]
