from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path("products/filters/", views.FilterOptionsView.as_view(), name="product-filters"),
    path("products/<int:pk>/reviews/", views.ProductReviewListCreateView.as_view(), name="product-reviews"),
    path("products/<str:lookup>/", views.ProductDetailView.as_view(), name="product-detail"),
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("brands/", views.BrandListView.as_view(), name="brand-list"),
    path("menu/", views.MenuView.as_view(), name="menu"),
    path("banners/", views.BannerListView.as_view(), name="banner-list"),
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
    path("wishlist/<int:product_id>/", views.WishlistDeleteView.as_view(), name="wishlist-delete"),
]
