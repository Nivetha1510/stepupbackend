from django.db import IntegrityError
from django.db.models import Count, Prefetch, Q
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (Banner, Brand, Category, Color, Product, ProductVariant, Review, Style,
                     WishlistItem, recalculate_rating)
from .serializers import (BannerSerializer, BrandSerializer, CategorySerializer, ProductDetailSerializer,
                          ProductListSerializer, ReviewSerializer, WishlistItemSerializer)

SORT_OPTIONS = {
    "featured": ["is_trending", "-created_at"],
    "new": ["-created_at"],
    "price_asc": ["price", "name"],
    "price_desc": ["-price", "name"],
    "rating": ["-rating", "-rating_count"],
    "name_asc": ["name"],
    "name_desc": ["-name"],
}


def active_products():
    variants = ProductVariant.objects.select_related("color")
    return (Product.objects.filter(status=Product.STATUS_ACTIVE)
            .select_related("category", "brand", "style")
            .prefetch_related(Prefetch("variants", queryset=variants)))


def split_param(request, name):
    raw = request.query_params.get(name, "")
    return [v.strip() for v in raw.split(",") if v.strip()]


class ProductListView(generics.ListAPIView):
    """
    GET /api/products/
      ?category=womens  &brand=lilley,xl  &style=sandals  &size=41  &color=black
      &q=search text    &sort=featured|new|price_asc|price_desc|rating|name_asc|name_desc
      &trending=1       &offers=1         &page=2
    """

    serializer_class = ProductListSerializer

    def get_queryset(self):
        qs = active_products()
        req = self.request
        if category := req.query_params.get("category"):
            qs = qs.filter(category__slug=category)
        if brands := split_param(req, "brand"):
            qs = qs.filter(brand__slug__in=brands)
        if styles := split_param(req, "style"):
            qs = qs.filter(style__slug__in=styles)
        if sizes := split_param(req, "size"):
            qs = qs.filter(variants__size__in=sizes, variants__stock__gt=0)
        if colors := split_param(req, "color"):
            qs = qs.filter(variants__color__name__in=colors)
        if q := req.query_params.get("q", "").strip():
            qs = qs.filter(
                Q(name__icontains=q) | Q(brand__name__icontains=q) | Q(style__name__icontains=q)
                | Q(category__name__icontains=q) | Q(description__icontains=q)
            )
        if req.query_params.get("trending") in ("1", "true"):
            qs = qs.filter(is_trending=True)
        if req.query_params.get("offers") in ("1", "true"):
            qs = qs.filter(discount_price__isnull=False)
        if min_price := req.query_params.get("min_price"):
            qs = qs.filter(price__gte=min_price)
        if max_price := req.query_params.get("max_price"):
            qs = qs.filter(price__lte=max_price)
        sort = req.query_params.get("sort", "featured")
        return qs.distinct().order_by(*SORT_OPTIONS.get(sort, SORT_OPTIONS["featured"]), "id")


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer

    def get_queryset(self):
        return active_products().prefetch_related("images")

    def get_object(self):
        # Accept either numeric id or slug: /api/products/12/ or /api/products/harlan-mens-tan-boat-shoe/
        lookup = self.kwargs["lookup"]
        qs = self.get_queryset()
        obj = qs.filter(pk=lookup).first() if lookup.isdigit() else qs.filter(slug=lookup).first()
        if obj is None:
            from django.http import Http404
            raise Http404("Product not found.")
        return obj


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        return Category.objects.annotate(
            product_count=Count("products", filter=Q(products__status=Product.STATUS_ACTIVE))
        )


class BrandListView(generics.ListAPIView):
    serializer_class = BrandSerializer
    pagination_class = None
    queryset = Brand.objects.all()


class FilterOptionsView(APIView):
    """Options for the Style / Size / Brands / Color dropdowns, scoped to a category."""

    def get(self, request):
        products = Product.objects.filter(status=Product.STATUS_ACTIVE)
        if category := request.query_params.get("category"):
            products = products.filter(category__slug=category)
        variants = ProductVariant.objects.filter(product__in=products)
        sizes = sorted(set(variants.values_list("size", flat=True)), key=lambda s: (len(s), s))
        colors = Color.objects.filter(variants__in=variants).distinct().values("name", "hex_code")
        styles = Style.objects.filter(products__in=products).distinct().values("name", "slug")
        brands = Brand.objects.filter(products__in=products).distinct().values("name", "slug")
        return Response({
            "styles": list(styles),
            "sizes": sizes,
            "brands": list(brands),
            "colors": list(colors),
        })


class MenuView(APIView):
    """Data for the Womens / Mens / Kids / Brands mega-menus."""

    def get(self, request):
        styles = list(Style.objects.values("name", "slug"))
        brands = list(Brand.objects.values("name", "slug"))
        return Response({"styles": styles, "brands": brands})


class BannerListView(generics.ListAPIView):
    serializer_class = BannerSerializer
    pagination_class = None
    queryset = Banner.objects.filter(is_active=True)


class ProductReviewListCreateView(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_product(self):
        return generics.get_object_or_404(Product, pk=self.kwargs["pk"], status=Product.STATUS_ACTIVE)

    def get_queryset(self):
        return Review.objects.filter(product_id=self.kwargs["pk"], is_approved=True).select_related("user")

    def perform_create(self, serializer):
        product = self.get_product()
        if Review.objects.filter(product=product, user=self.request.user).exists():
            raise ValidationError({"detail": "You have already reviewed this product."})
        serializer.save(product=product, user=self.request.user)
        recalculate_rating(product)


class WishlistView(generics.ListCreateAPIView):
    serializer_class = WishlistItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return WishlistItem.objects.filter(user=self.request.user).select_related(
            "product__category", "product__brand", "product__style"
        ).prefetch_related("product__variants__color")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item, created = WishlistItem.objects.get_or_create(
                user=request.user, product=serializer.validated_data["product"]
            )
        except IntegrityError:
            created = False
            item = WishlistItem.objects.get(user=request.user, product=serializer.validated_data["product"])
        return Response(self.get_serializer(item).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WishlistDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, product_id):
        deleted, _ = WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
        if not deleted:
            return Response({"detail": "Not in wishlist."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
