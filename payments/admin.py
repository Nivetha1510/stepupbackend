from django.contrib import admin, messages

from orders.models import Order
from .models import Payment
from .services import mark_paid


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["order", "method", "status", "amount", "transaction_reference", "created_at"]
    list_filter = ["method", "status"]
    search_fields = ["order__order_number", "transaction_reference", "gateway_order_id"]
    readonly_fields = ["order", "method", "amount", "transaction_reference", "gateway_order_id", "created_at", "updated_at"]
    actions = ["confirm_payment_received"]

    @admin.action(description="Mark selected UPI payments as paid (money received in the bank)")
    def confirm_payment_received(self, request, queryset):
        done = 0
        for payment in queryset.select_related("order").filter(method=Order.METHOD_UPI):
            if payment.status == Order.PAYMENT_PENDING and payment.transaction_reference:
                mark_paid(payment.order, payment.transaction_reference)
                done += 1
        skipped = queryset.count() - done
        self.message_user(request, f"{done} payment(s) marked as paid.", messages.SUCCESS)
        if skipped:
            self.message_user(request, f"{skipped} skipped: only pending UPI payments with a customer reference can be confirmed.",
                              messages.WARNING)
