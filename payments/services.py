import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from orders.models import Order
from .models import Payment

logger = logging.getLogger(__name__)

API_URL = "https://api.razorpay.com/v1/orders"


class GatewayUnavailable(APIException):
    status_code = 502
    default_detail = "The payment service is not reachable right now. Please try again."


def razorpay_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _signature(message, secret):
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _paise(amount):
    return int((Decimal(amount) * 100).to_integral_value())


def _post_order(order, payment):
    body = json.dumps({
        "amount": _paise(payment.amount), "currency": "INR", "receipt": order.order_number,
        "notes": {"order_id": str(order.pk), "order_number": order.order_number},
    }).encode()
    token = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    req = urllib.request.Request(API_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.load(res)
    except urllib.error.HTTPError as exc:
        logger.error("Razorpay order creation failed: %s %s", exc.code, exc.read()[:300])
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.error("Razorpay order creation failed: %s", exc)
    raise GatewayUnavailable()


def start_payment(order):
    """Create (or reuse) the Razorpay order for an unpaid order and return what the browser needs."""
    if not razorpay_configured():
        raise ValidationError({"detail": "Online payment is not available right now."})
    payment = Payment.objects.get(order=order)
    if order.payment_method != Order.METHOD_RAZORPAY or order.status == Order.STATUS_CANCELLED:
        raise ValidationError({"detail": "This order is not payable online."})
    if payment.status == Order.PAYMENT_PAID:
        raise ValidationError({"detail": "This order is already paid."})
    if not payment.gateway_order_id:
        gateway = _post_order(order, payment)
        payment.gateway_order_id = gateway["id"]
        payment.save(update_fields=["gateway_order_id", "updated_at"])
    return {
        "key": settings.RAZORPAY_KEY_ID, "gateway_order_id": payment.gateway_order_id,
        "amount": _paise(payment.amount), "currency": "INR", "order_number": order.order_number,
        "name": f"{order.first_name} {order.last_name}".strip(), "email": order.email, "phone": order.phone,
    }


@transaction.atomic
def mark_paid(order, gateway_payment_id):
    order = Order.objects.select_for_update().get(pk=order.pk)
    payment = Payment.objects.select_for_update().get(order=order)
    if payment.status == Order.PAYMENT_PAID:
        return order
    if order.status == Order.STATUS_CANCELLED:
        # Paid after the order was cancelled (stock already released): leave for manual refund.
        logger.warning("Payment %s received for cancelled order %s; refund manually.", gateway_payment_id, order.order_number)
        return order
    payment.status = Order.PAYMENT_PAID
    payment.transaction_reference = gateway_payment_id[:64]
    payment.save(update_fields=["status", "transaction_reference", "updated_at"])
    order.payment_status = Order.PAYMENT_PAID
    order.save(update_fields=["payment_status", "updated_at"])
    return order


def verify_payment(order, gateway_order_id, gateway_payment_id, signature):
    """Check Razorpay's signature for a completed checkout, then mark the order paid."""
    payment = Payment.objects.get(order=order)
    expected = _signature(f"{gateway_order_id}|{gateway_payment_id}", settings.RAZORPAY_KEY_SECRET)
    if (not payment.gateway_order_id or payment.gateway_order_id != gateway_order_id
            or not hmac.compare_digest(expected, signature or "")):
        raise ValidationError({"detail": "Payment could not be verified."})
    return mark_paid(order, gateway_payment_id)


def webhook_signature_ok(raw_body, signature):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    return bool(secret) and hmac.compare_digest(_signature(raw_body.decode(), secret), signature or "")
