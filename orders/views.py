from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Address
from cart.services import get_cart
from .models import Order
from .serializers import CheckoutSerializer, OrderSerializer
from .services import cancel_order, create_order_from_cart


def user_orders(user):
    return (Order.objects.filter(user=user)
            .select_related("payment").prefetch_related("items__product", "history"))


class OrderListCreateView(generics.ListAPIView):
    """
    GET  /api/orders/  — the signed-in customer's order history
    POST /api/orders/  — place an order from the current cart
    """

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return user_orders(self.request.user)

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        key = (request.headers.get("X-Idempotency-Key") or "").strip()[:64] or None
        order, created = create_order_from_cart(
            user=request.user, cart=get_cart(request), data=data, idempotency_key=key
        )
        if created and data.get("save_address"):
            full_name = f"{data['first_name']} {data['last_name']}".strip()
            exists = Address.objects.filter(user=request.user, address_line1=data["address_line1"],
                                            pincode=data["pincode"]).exists()
            if not exists:
                Address.objects.create(
                    user=request.user, full_name=full_name, phone=data["phone"],
                    address_line1=data["address_line1"], city=data["city"], state=data["state"],
                    landmark=data.get("landmark", ""), pincode=data["pincode"],
                    is_default=not Address.objects.filter(user=request.user).exists(),
                )
        order = user_orders(request.user).get(pk=order.pk)
        return Response(OrderSerializer(order, context={"request": request}).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Scoped to the requesting user: another customer's order id returns 404.
        return user_orders(self.request.user)


class OrderCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = generics.get_object_or_404(Order, pk=pk, user=request.user)
        order = cancel_order(order)
        order = user_orders(request.user).get(pk=order.pk)
        return Response(OrderSerializer(order, context={"request": request}).data)
