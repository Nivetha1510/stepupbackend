from django.contrib import admin

from .models import ContactMessage, NewsletterSubscriber


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "phone", "created_at", "is_resolved"]
    list_editable = ["is_resolved"]
    list_filter = ["is_resolved"]
    search_fields = ["name", "email", "message"]
    readonly_fields = ["name", "email", "phone", "message", "created_at"]


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ["email", "created_at"]
    search_fields = ["email"]
