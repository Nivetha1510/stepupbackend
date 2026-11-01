from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Address, Profile

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    accept_terms = serializers.BooleanField()

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("Please accept the Terms and Conditions and Privacy Policy.")
        return value

    def validate_password(self, value):
        # Field-level so password problems are reported even when other fields also fail.
        email = str(self.initial_data.get("email", ""))
        validate_password(value, user=User(username=email, email=email))
        return value

    def create(self, validated):
        user = User.objects.create_user(
            username=validated["email"],
            email=validated["email"],
            password=validated["password"],
            first_name=validated.get("first_name", ""),
            last_name=validated.get("last_name", ""),
        )
        Profile.objects.create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class UserSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source="profile.phone", required=False, allow_blank=True, max_length=15)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "is_staff", "date_joined"]
        read_only_fields = ["id", "email", "is_staff", "date_joined"]

    def validate_phone(self, value):
        from .models import phone_validator

        if value:
            phone_validator(value)
        return value

    def update(self, instance, validated):
        profile_data = validated.pop("profile", {})
        for field, value in validated.items():
            setattr(instance, field, value)
        instance.save()
        if profile_data:
            profile, _ = Profile.objects.get_or_create(user=instance)
            profile.phone = profile_data.get("phone", profile.phone)
            profile.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        validate_password(attrs["new_password"], user=user)
        return attrs


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["id", "full_name", "phone", "address_line1", "city", "state", "landmark", "pincode",
                  "is_default", "created_at"]
        read_only_fields = ["id", "created_at"]
