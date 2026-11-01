from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from urllib.parse import urlencode
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
import hashlib
import logging
import secrets

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import authenticate, get_user_model
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from cart.services import merge_guest_cart
from .models import Address, Profile, GoogleAccount
from .serializers import (AddressSerializer, ChangePasswordSerializer, LoginSerializer,
                          RegisterSerializer, UserSerializer)

User = get_user_model()


def auth_response(user, request, http_status=status.HTTP_200_OK):
    token, _ = Token.objects.get_or_create(user=user)
    # Move any guest cart items into the user's cart.
    merge_guest_cart(user, request.headers.get("X-Cart-Token"))
    Profile.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data}, status=http_status)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return auth_response(user, request, status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        account = User.objects.filter(email__iexact=email).first()
        user = None
        if account is not None:
            user = authenticate(request, username=account.username,
                                password=serializer.validated_data["password"])
        if user is None:
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active:
            return Response({"detail": "This account is disabled."}, status=status.HTTP_403_FORBIDDEN)
        return auth_response(user, request)


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        credential = request.data.get("credential")

        if not isinstance(credential, str) or not credential:
            return Response(
                {"detail": "Google credential is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not settings.GOOGLE_CLIENT_ID:
            return Response(
                {"detail": "Google login is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        try:
            payload = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
        except ValueError:
            return Response(
                {"detail": "Invalid Google credential."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        google_sub = payload.get("sub")
        email = (payload.get("email") or "").strip().lower()
        email_verified = payload.get("email_verified") is True

        if not google_sub or not email or not email_verified:
            return Response(
                {"detail": "A verified Google account is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Returning Google customer
        linked = GoogleAccount.objects.select_related("user").filter(
            google_sub=google_sub
        ).first()

        if linked:
            if not linked.user.is_active:
                return Response(
                    {"detail": "This account is disabled."},
                    status=status.HTTP_403_FORBIDDEN
                )
            return auth_response(linked.user, request)

        # Do not automatically link an existing password account.
        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {
                    "detail": (
                        "An account with this email already exists. "
                        "Please log in with your existing method."
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        # Create a new customer and link their Google identity.
        with transaction.atomic():
            username = "google_" + secrets.token_hex(12)

            user = User(username=username, email=email)
            user.set_unusable_password()
            user.save()

            GoogleAccount.objects.create(
                user=user,
                google_sub=google_sub
            )

        return auth_response(user, request)



class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Logged out."})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        Profile.objects.get_or_create(user=self.request.user)
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        # Rotate the token so other sessions are signed out.
        Token.objects.filter(user=request.user).delete()
        token = Token.objects.create(user=request.user)
        return Response({"detail": "Password updated.", "token": token.key})


class AddressListCreateView(generics.ListCreateAPIView):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        first = not Address.objects.filter(user=self.request.user).exists()
        serializer.save(user=self.request.user, is_default=serializer.validated_data.get("is_default") or first)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Customers can only ever see their own addresses.
        return Address.objects.filter(user=self.request.user)


logger = logging.getLogger(__name__)

# One reset email per address per minute, on top of the per-IP throttle (stops mail-bombing one inbox).
RESET_EMAIL_COOLDOWN = 60


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        email = request.data.get("email", "")

        if not isinstance(email, str) or not email.strip():
            return Response(
                {"detail": "Please enter your email address."},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = email.strip().lower()

        # Same response for registered and unregistered emails.
        message = {
            "detail": "If an eligible account exists, a password reset link has been sent."
        }

        user = User.objects.filter(
            email__iexact=email,
            is_active=True
        ).first()

        # Google-only accounts have unusable passwords.
        cooldown_key = "pwreset:" + hashlib.sha256(email.encode()).hexdigest()
        if user and user.has_usable_password() and cache.add(cooldown_key, 1, RESET_EMAIL_COOLDOWN):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            query = urlencode({"uid": uid, "token": token})
            reset_link = (
                f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?{query}"
            )

            try:
                send_mail(
                    subject="Reset your StepUp password",
                    message=(
                        "Hello,\n\n"
                        "We received a request to reset your StepUp password.\n\n"
                        f"Use this link:\n{reset_link}\n\n"
                        f"It expires in {max(settings.PASSWORD_RESET_TIMEOUT // 60, 1)} minutes and can be used once.\n"
                        "If you did not request this, ignore this email."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False
                )
            except Exception as exc:
                # Never fail (or log the link/email) here: an error only for registered addresses would reveal them.
                logger.error("Password reset email could not be sent (user id %s): %s", user.pk, type(exc).__name__)

        return Response(message)

class ResetPasswordConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset_confirm"

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")

        if not all(
            isinstance(value, str) and value
            for value in [uid, token, password, confirm_password]
        ):
            return Response(
                {"detail": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if password != confirm_password:
            return Response(
                {"detail": "Passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            return Response(
                {"detail": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if (
            not user.has_usable_password()
            or not default_token_generator.check_token(user, token)
        ):
            return Response(
                {"detail": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            return Response(
                {"password": exc.messages},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(password)
        user.save(update_fields=["password"])

        # Invalidate existing API tokens after password reset.
        Token.objects.filter(user=user).delete()

        return Response({
            "detail": "Password reset successful. Please log in."
        })

