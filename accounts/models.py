from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(r"^\+?[0-9]{10,13}$", "Enter a valid phone number (10–13 digits).")
pincode_validator = RegexValidator(r"^[0-9]{6}$", "Enter a valid 6-digit pincode.")


class Profile(models.Model):
    """Extra customer information attached to Django's built-in User."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=15, blank=True, validators=[phone_validator])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile of {self.user.email or self.user.username}"


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15, validators=[phone_validator])
    address_line1 = models.CharField(max_length=255)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    landmark = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=6, validators=[pincode_validator])
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.full_name}, {self.city} - {self.pincode}"

    def save(self, *args, **kwargs):
        # Only one default address per user.
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

class GoogleAccount(models.Model):
    """Links a verified Google identity to a StepUp customer."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_account"
    )

    google_sub = models.CharField(
        max_length=255,
        unique=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Google account for {self.user.username}"
