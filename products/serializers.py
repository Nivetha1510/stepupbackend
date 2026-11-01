from rest_framework import serializers

from .models import (Banner, Brand, Category, Color, Product, ProductImage, ProductVariant, Review,
                     WishlistItem)


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "image", "product_count"]


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "slug"]


class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ["id", "name", "hex_code"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text"]


class VariantSerializer(serializers.ModelSerializer):
    color = ColorSerializer(read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "size", "color", "stock", "sku"]


def product_colors(product):
    seen, colors = set(), []
    for v in product.variants.all():
        if v.color_id not in seen:
            seen.add(v.color_id)
            colors.append({"id": v.color.id, "name": v.color.name, "hex_code": v.color.hex_code})
    return colors


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    brand = serializers.CharField(source="brand.name", default=None, read_only=True)
    style = serializers.CharField(source="style.name", default=None, read_only=True)
    selling_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    colors = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "slug", "category", "brand", "style", "price", "discount_price",
                  "selling_price", "image", "rating", "rating_count", "colors", "in_stock", "is_trending",
                  "created_at"]

    def get_colors(self, obj):
        return product_colors(obj)

    def get_in_stock(self, obj):
        return any(v.stock > 0 for v in obj.variants.all())


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "reviewer", "title", "location", "rating", "fit", "comfort", "value_for_money",
                  "quality", "comment", "recommend", "created_at"]
        read_only_fields = ["id", "reviewer", "created_at"]

    def get_reviewer(self, obj):
        return obj.user.first_name or obj.user.email.split("@")[0]


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = VariantSerializer(many=True, read_only=True)
    sizes = serializers.SerializerMethodField()
    total_stock = serializers.IntegerField(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description", "images", "variants", "sizes", "total_stock", "category_name",
        ]

    def get_sizes(self, obj):
        sizes = sorted({v.size for v in obj.variants.all()}, key=lambda s: (len(s), s))
        return sizes


class WishlistItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(status=Product.STATUS_ACTIVE), source="product", write_only=True
    )

    class Meta:
        model = WishlistItem
        fields = ["id", "product", "product_id", "created_at"]
        read_only_fields = ["id", "created_at"]


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ["id", "title", "image", "link"]
