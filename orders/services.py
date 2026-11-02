import secrets

from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import ValidationError

from cart.services import cart_totals
from payments.models import Payment
from payments.services import razorpay_configured, upi_configured
from products.models import Product, ProductVariant
from .models import Order, OrderItem


@transaction.atomic
def create_order_from_cart(*, user, cart, data, idempotency_key=None):
    """
    Turn the cart into an order. Prices and totals are recalculated here on the
    server; anything the browser sent about prices is ignored. Stock rows are
    locked so two customers can't buy the last pair at the same time.
    """
    if idempotency_key:
        existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
        if existing:
            return existing, False

    items = list(cart.items.select_related("variant__product__brand", "variant__color")) if cart else []
    if not items:
        raise ValidationError({"detail": "Your cart is empty."})

    variant_ids = sorted(i.variant_id for i in items)
    locked = {v.id: v for v in ProductVariant.objects.select_for_update().filter(id__in=variant_ids).order_by("id")}

    problems = []
    for item in items:
        v = locked[item.variant_id]
        if v.product.status != Product.STATUS_ACTIVE:
            problems.append(f"{v.product.name} is no longer available.")
        elif v.stock < item.quantity:
            problems.append(f"{v.product.name} (size {v.size}) — only {v.stock} left.")
    if problems:
        raise ValidationError({"detail": "Some items in your cart need attention.", "items": problems})

    subtotal, shipping, total = cart_totals(items)

    order = Order.objects.create(
        user=user,
        payment_method=data["payment_method"],
        first_name=data["first_name"], last_name=data["last_name"], email=data["email"], phone=data["phone"],
        address_line1=data["address_line1"], city=data["city"], state=data["state"],
        landmark=data.get("landmark", ""), pincode=data["pincode"],
        subtotal=subtotal, shipping_cost=shipping, total=total,
        idempotency_key=idempotency_key or None,
    )

    for item in items:
        v = locked[item.variant_id]
        product = v.product
        OrderItem.objects.create(
            order=order, product=product, variant=v, product_name=product.name,
            brand_name=product.brand.name if product.brand else "", size=v.size, color=v.color.name,
            image=product.image.name if product.image else "", quantity=item.quantity,
            unit_price=product.selling_price,
        )
        ProductVariant.objects.filter(pk=v.pk).update(stock=F("stock") - item.quantity)

    if data["payment_method"] == Order.METHOD_RAZORPAY and not razorpay_configured():
        raise ValidationError({"payment_method": "Online payment is not available right now."})

    if data["payment_method"] == Order.METHOD_UPI and not upi_configured():
        raise ValidationError({"payment_method": "UPI payment is not available right now."})

    if data["payment_method"] == Order.METHOD_DEMO:
        # Demo online payment: no card data is collected; we simply mark it paid with a demo reference.
        payment_status, reference = Order.PAYMENT_PAID, f"DEMO-{secrets.token_hex(6).upper()}"
    else:
        payment_status, reference = Order.PAYMENT_PENDING, ""
    Payment.objects.create(order=order, method=data["payment_method"], status=payment_status,
                           amount=total, transaction_reference=reference)
    if payment_status != order.payment_status:
        Order.objects.filter(pk=order.pk).update(payment_status=payment_status)
        order.payment_status = payment_status

    cart.items.all().delete()
    return order, True


@transaction.atomic
def restock_order(order):
    """Put the items of a cancelled order back into stock."""
    for item in order.items.select_related("variant"):
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(stock=F("stock") + item.quantity)


@transaction.atomic
def cancel_order(order, note="Cancelled by customer"):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_cancel:
        raise ValidationError({"detail": "This order can no longer be cancelled."})
    restock_order(order)
    order.status = Order.STATUS_CANCELLED
    if order.payment_status == Order.PAYMENT_PAID:
        order.payment_status = Order.PAYMENT_REFUNDED
    elif order.payment_status == Order.PAYMENT_PENDING:
        order.payment_status = Order.PAYMENT_FAILED
    order.save()
    order.history.filter(status=Order.STATUS_CANCELLED).update(note=note)
    Payment.objects.filter(order=order).update(status=order.payment_status)
    return order
