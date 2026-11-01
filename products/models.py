from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils.text import slugify


def unique_slug(instance, value, field="slug"):
    base = slugify(value)[:180] or "item"
    slug, n = base, 2
    model = instance.__class__
    while model.objects.filter(**{field: slug}).exclude(pk=instance.pk).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Category(models.Model):
    """Top-level shopping category: Womens, Mens, Kids."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Brand(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Style(models.Model):
    """Shoe style shown in the mega-menu (Sandals, Trainers, Boots...)."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Color(models.Model):
    name = models.CharField(max_length=40, unique=True)
    hex_code = models.CharField(max_length=7, help_text="e.g. #000000. Leave blank for 'Multi-color'.", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_DRAFT = "draft"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_DRAFT, "Draft"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=190, unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("1"))], help_text="MRP in ₹")
    discount_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("1"))],
        help_text="Optional sale price in ₹ (must be lower than MRP)",
    )
    image = models.ImageField(upload_to="products/", help_text="Main card image")
    rating = models.DecimalField(
        max_digits=2, decimal_places=1, default=Decimal("0"),
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Average rating shown on the card (updated automatically when reviews are added)",
    )
    rating_count = models.PositiveIntegerField(default=0)
    is_trending = models.BooleanField(default=False, help_text="Show in 'New & Trending' on the home page")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["price"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(discount_price__isnull=True) | models.Q(discount_price__lt=models.F("price")),
                name="discount_below_price",
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)

    @property
    def selling_price(self):
        return self.discount_price if self.discount_price else self.price

    @property
    def total_stock(self):
        return self.variants.aggregate(total=Sum("stock"))["total"] or 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=160, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductVariant(models.Model):
    """A size + colour combination with its own stock level."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=10)
    color = models.ForeignKey(Color, on_delete=models.PROTECT, related_name="variants")
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=60, unique=True, blank=True)

    class Meta:
        ordering = ["product", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "size", "color"], name="unique_variant"),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.color.name} / {self.size}"

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f"SU-{self.product_id}-{slugify(self.color.name)[:6].upper()}-{self.size}"
        super().save(*args, **kwargs)


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    title = models.CharField(max_length=100)
    location = models.CharField(max_length=80, blank=True)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    fit = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comfort = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    value_for_money = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    quality = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(max_length=2000)
    recommend = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="one_review_per_user")]

    def __str__(self):
        return f"{self.title} ({self.rating}★) on {self.product.name}"


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_item")]

    def __str__(self):
        return f"{self.user} ♥ {self.product}"


class Banner(models.Model):
    """Home-page hero carousel slide, managed from the admin."""

    title = models.CharField(max_length=160)
    image = models.ImageField(upload_to="banners/")
    link = models.CharField(max_length=200, blank=True, help_text="Frontend path, e.g. /shop/womens")
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title


def recalculate_rating(product):
    from django.db.models import Avg, Count

    agg = product.reviews.filter(is_approved=True).aggregate(avg=Avg("rating"), n=Count("id"))
    if agg["n"]:
        product.rating = Decimal(str(round(agg["avg"], 1)))
        product.rating_count = agg["n"]
        product.save(update_fields=["rating", "rating_count", "updated_at"])
