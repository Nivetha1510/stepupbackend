from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CartItem
from .serializers import AddItemSerializer, UpdateItemSerializer, serialize_cart
from .services import get_cart


def stock_error(variant, wanted):
    if variant.stock <= 0:
        return f"Sorry, size {variant.size} in {variant.color.name} is out of stock."
    return f"Only {variant.stock} left in size {variant.size}. You asked for {wanted}."


class CartView(APIView):
    """GET /api/cart/ — the current user's (or guest's) cart, with prices re-read from the database."""

    def get(self, request):
        return Response(serialize_cart(get_cart(request), request))

    def delete(self, request):
        cart = get_cart(request)
        if cart:
            cart.items.all().delete()
        return Response(serialize_cart(cart, request))


class CartItemCreateView(APIView):
    """POST /api/cart/items/ {variant, quantity}"""

    @transaction.atomic
    def post(self, request):
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        variant = serializer.validated_data["variant"]
        qty = serializer.validated_data["quantity"]
        cart = get_cart(request, create=True)
        item = CartItem.objects.select_for_update().filter(cart=cart, variant=variant).first()
        new_qty = (item.quantity if item else 0) + qty
        if new_qty > settings.MAX_ITEM_QUANTITY:
            return Response({"detail": f"You can buy at most {settings.MAX_ITEM_QUANTITY} of one item."},
                            status=status.HTTP_400_BAD_REQUEST)
        if new_qty > variant.stock:
            return Response({"detail": stock_error(variant, new_qty)}, status=status.HTTP_400_BAD_REQUEST)
        if item:
            item.quantity = new_qty
            item.save(update_fields=["quantity"])
        else:
            CartItem.objects.create(cart=cart, variant=variant, quantity=qty)
        cart.save(update_fields=["updated_at"])
        return Response(serialize_cart(cart, request), status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    """PATCH/DELETE /api/cart/items/{id}/"""

    def get_item(self, request, pk):
        cart = get_cart(request)
        if cart is None:
            return None, None
        return cart, CartItem.objects.select_related("variant__color").filter(cart=cart, pk=pk).first()

    @transaction.atomic
    def patch(self, request, pk):
        cart, item = self.get_item(request, pk)
        if item is None:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        variant = serializer.validated_data.get("variant", item.variant)
        qty = serializer.validated_data.get("quantity", item.quantity)
        if variant.product_id != item.variant.product_id:
            return Response({"detail": "Variant belongs to a different product."}, status=status.HTTP_400_BAD_REQUEST)
        if qty > variant.stock:
            return Response({"detail": stock_error(variant, qty)}, status=status.HTTP_400_BAD_REQUEST)
        if variant.pk != item.variant_id:
            # Switching size: merge with an existing line for that size if there is one.
            other = CartItem.objects.filter(cart=cart, variant=variant).first()
            if other:
                other.quantity = min(other.quantity + qty, variant.stock, settings.MAX_ITEM_QUANTITY)
                other.save(update_fields=["quantity"])
                item.delete()
                return Response(serialize_cart(cart, request))
            item.variant = variant
        item.quantity = qty
        item.save()
        return Response(serialize_cart(cart, request))

    def delete(self, request, pk):
        cart, item = self.get_item(request, pk)
        if item is None:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(serialize_cart(cart, request))
