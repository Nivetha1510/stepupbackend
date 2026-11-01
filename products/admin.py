from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html

from .models import (Banner, Brand, Category, Color, Product, ProductImage, ProductVariant, Review, Style,
                     WishlistItem)


def thumb(image, size=60):
    if not image:
        return "—"
    return format_html('<img src="{}" style="height:{}px;width:{}px;object-fit:contain;'
                       'background:#eee;border-radius:6px" />', image.url, size, size)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["preview", "name", "slug", "display_order", "product_count"]
    list_display_links = ["preview", "name"]
    prepopulated_fields = {"slug": ["name"]}
    list_editable = ["display_order"]

    @admin.display(description="Image")
    def preview(self, obj):
        return thumb(obj.image, 48)

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Style)
class StyleAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "display_order"]
    list_editable = ["display_order"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ["swatch", "name", "hex_code"]
    list_display_links = ["swatch", "name"]
    search_fields = ["name"]

    @admin.display(description="")
    def swatch(self, obj):
        if not obj.hex_code:
            return "Multi"
        return format_html('<span style="display:inline-block;width:18px;height:18px;border-radius:4px;'
                           'border:1px solid #999;background:{}"></span>', obj.hex_code)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ["preview", "image", "alt_text", "display_order"]
    readonly_fields = ["preview"]

    @admin.display(description="Preview")
    def preview(self, obj):
        return thumb(obj.image)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ["color", "size", "stock", "sku"]
    readonly_fields = ["sku"]
    autocomplete_fields = ["color"]


class StockFilter(admin.SimpleListFilter):
    title = "availability"
    parameter_name = "availability"

    def lookups(self, request, model_admin):
        return [("in", "In stock"), ("low", "Low stock (≤ 5)"), ("out", "Out of stock")]

    def queryset(self, request, qs):
        qs = qs.annotate(_stock=Sum("variants__stock"))
        if self.value() == "in":
            return qs.filter(_stock__gt=0)
        if self.value() == "low":
            return qs.filter(_stock__gt=0, _stock__lte=5)
        if self.value() == "out":
            return qs.filter(_stock__lte=0) | qs.filter(_stock__isnull=True)
        return qs


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["preview", "name", "brand", "category", "style", "price", "discount_price", "stock",
                    "rating", "is_trending", "status"]
    list_display_links = ["preview", "name"]
    list_filter = ["category", "status", StockFilter, "is_trending", "style", "brand"]
    list_editable = ["is_trending", "status"]
    search_fields = ["name", "brand__name", "description"]
    prepopulated_fields = {"slug": ["name"]}
    autocomplete_fields = ["brand"]
    readonly_fields = ["large_preview", "created_at", "updated_at"]
    inlines = [ProductVariantInline, ProductImageInline]
    list_per_page = 30
    fieldsets = [
        (None, {"fields": ["name", "slug", "category", "brand", "style", "status", "is_trending"]}),
        ("Pricing", {"fields": ["price", "discount_price"]}),
        ("Content", {"fields": ["description", "image", "large_preview"]}),
        ("Rating", {"fields": ["rating", "rating_count"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("brand", "category", "style").annotate(
            _total_stock=Sum("variants__stock")
        )

    @admin.display(description="Image")
    def preview(self, obj):
        return thumb(obj.image)

    @admin.display(description="Current image")
    def large_preview(self, obj):
        return thumb(obj.image, 180)

    @admin.display(description="Stock", ordering="_total_stock")
    def stock(self, obj):
        total = obj._total_stock or 0
        colour = "#b00020" if total == 0 else ("#c77700" if total <= 5 else "#2F4F4F")
        return format_html('<b style="color:{}">{}</b>', colour, total)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "color", "size", "stock"]
    list_editable = ["stock"]
    list_filter = ["product__category", "color", "size"]
    search_fields = ["sku", "product__name"]
    autocomplete_fields = ["product", "color"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["title", "product", "user", "rating", "recommend", "is_approved", "created_at"]
    list_filter = ["is_approved", "rating", "recommend"]
    list_editable = ["is_approved"]
    search_fields = ["title", "comment", "product__name", "user__email"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .models import recalculate_rating
        recalculate_rating(obj.product)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "created_at"]
    search_fields = ["user__email", "product__name"]


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ["preview", "title", "link", "display_order", "is_active"]
    list_display_links = ["preview", "title"]
    list_editable = ["display_order", "is_active"]

    @admin.display(description="Image")
    def preview(self, obj):
        return format_html('<img src="{}" style="height:50px;border-radius:6px" />', obj.image.url) if obj.image else "—"
