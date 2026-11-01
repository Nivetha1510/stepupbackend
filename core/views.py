from django.db import connection
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import ContactMessage, NewsletterSubscriber


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "message"]


class ContactView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Thanks! We'll get back to you soon."}, status=status.HTTP_201_CREATED)


class NewsletterView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        email = serializers.EmailField().run_validation(request.data.get("email", ""))
        _, created = NewsletterSubscriber.objects.get_or_create(email=email.lower())
        message = "You're subscribed!" if created else "You're already on the list."
        return Response({"detail": message}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class HealthView(APIView):
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok", "database": connection.vendor})
