from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ["phone"]


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0
    fields = ["full_name", "phone", "address_line1", "city", "state", "pincode", "is_default"]


admin.site.unregister(User)


@admin.register(User)
class CustomerAdmin(BaseUserAdmin):
    inlines = [ProfileInline, AddressInline]
    list_display = ["email", "first_name", "last_name", "phone", "order_count", "is_staff", "is_active",
                    "date_joined"]
    search_fields = ["email", "username", "first_name", "last_name", "profile__phone"]

    @admin.display(description="Phone")
    def phone(self, obj):
        return getattr(getattr(obj, "profile", None), "phone", "")

    @admin.display(description="Orders")
    def order_count(self, obj):
        return obj.orders.count()


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["full_name", "user", "city", "state", "pincode", "is_default"]
    search_fields = ["full_name", "user__email", "city", "pincode"]
    list_filter = ["state"]
