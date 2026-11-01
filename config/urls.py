from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from core.views import ContactView, HealthView, NewsletterView

admin.site.site_header = "StepUp.in Administration"
admin.site.site_title = "StepUp Admin"
admin.site.index_title = "Store management"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("products.urls")),
    path("api/", include("cart.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("payments.urls")),
    path("api/contact/", ContactView.as_view(), name="contact"),
    path("api/newsletter/", NewsletterView.as_view(), name="newsletter"),
    path("api/health/", HealthView.as_view(), name="health"),
]

if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
