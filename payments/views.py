import json

from rest_framework import permissions
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order
from orders.serializers import OrderSerializer
from orders.views import user_orders
from .models import Payment
from .services import mark_paid, razorpay_configured, start_payment, verify_payment, webhook_signature_ok


class PaymentConfigView(APIView):
    """GET /api/payments/config/ — tells the checkout page whether real online payment is available."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"online_enabled": razorpay_configured()})


class StartPaymentView(APIView):
    """POST /api/payments/start/ {order_id} — create the Razorpay order for the checkout popup."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        order = get_object_or_404(Order, pk=request.data.get("order_id"), user=request.user)
        return Response(start_payment(order))


class VerifyPaymentView(APIView):
    """POST /api/payments/verify/ — confirm a completed payment using Razorpay's signature."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        order = get_object_or_404(Order, pk=request.data.get("order_id"), user=request.user)
        verify_payment(order, request.data.get("razorpay_order_id", ""), request.data.get("razorpay_payment_id", ""),
                       request.data.get("razorpay_signature", ""))
        order = user_orders(request.user).get(pk=order.pk)
        return Response(OrderSerializer(order, context={"request": request}).data)


class RazorpayWebhookView(APIView):
    """
    POST /api/payments/webhook/ — Razorpay calls this when a payment is captured, so an order is still
    marked paid if the customer closes the tab right after paying.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw = request.body
        if not webhook_signature_ok(raw, request.headers.get("X-Razorpay-Signature", "")):
            return Response({"detail": "Invalid signature."}, status=400)
        event = json.loads(raw or b"{}")
        entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        if event.get("event") in ("payment.captured", "order.paid") and entity.get("order_id"):
            payment = Payment.objects.filter(gateway_order_id=entity["order_id"]).select_related("order").first()
            if payment:
                mark_paid(payment.order, entity.get("id", ""))
        return Response({"status": "ok"})
