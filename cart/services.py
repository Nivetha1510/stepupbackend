"""Cart helpers shared by cart views, login and checkout."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from .models import Cart, CartItem


def parse_token(raw):
    try:
        return uuid.UUID(str(raw)) if raw else None
    except (ValueError, TypeError):
        return None


def get_cart(request, create=False):
    """Return the cart for this request (user cart if logged in, otherwise guest cart by token)."""
    if request.user and request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart is None:
            # Adopt the guest cart if one is being sent, otherwise create.
            merge_guest_cart(request.user, request.headers.get("X-Cart-Token"))
            cart = Cart.objects.filter(user=request.user).first()
            if cart is None and create:
                cart = Cart.objects.create(user=request.user)
        return cart

    token = parse_token(request.headers.get("X-Cart-Token"))
    cart = Cart.objects.filter(token=token, user__isnull=True).first() if token else None
    if cart is None and create:
        cart = Cart.objects.create()
    return cart


@transaction.atomic
def merge_guest_cart(user, raw_token):
    """Move items from a guest cart into the user's cart (called after login/register)."""
    token = parse_token(raw_token)
    guest = Cart.objects.select_for_update().filter(token=token, user__isnull=True).first() if token else None
    user_cart = Cart.objects.filter(user=user).first()
    if guest is None:
        return user_cart
    if user_cart is None:
        guest.user = user
        guest.save(update_fields=["user", "updated_at"])
        return guest
    for item in guest.items.select_related("variant"):
        existing = CartItem.objects.filter(cart=user_cart, variant=item.variant).first()
        if existing:
            existing.quantity = min(existing.quantity + item.quantity, settings.MAX_ITEM_QUANTITY,
                                    max(item.variant.stock, 1))
            existing.save(update_fields=["quantity"])
        else:
            item.cart = user_cart
            item.save(update_fields=["cart"])
    guest.delete()
    return user_cart


def shipping_for(subtotal):
    if subtotal <= 0:
        return Decimal("0")
    if subtotal >= settings.FREE_SHIPPING_THRESHOLD:
        return Decimal("0")
    return Decimal(settings.STANDARD_SHIPPING_FEE)


def cart_totals(items):
    subtotal = sum((i.line_total for i in items), Decimal("0"))
    shipping = shipping_for(subtotal)
    return subtotal, shipping, subtotal + shipping
