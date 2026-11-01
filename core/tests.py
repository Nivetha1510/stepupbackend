"""End-to-end API tests for the StepUp backend: auth, catalogue, cart, checkout, permissions."""
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from orders.models import Order
from products.models import Brand, Category, Color, Product, ProductVariant, Style

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()
GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
       b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


@override_settings(MEDIA_ROOT=TMP_MEDIA, REST_FRAMEWORK={
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 12,
})
class StoreAPITests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()  # throttle counters are cached; don't let one test's requests count against the next
        self.mens = Category.objects.create(name="Mens", slug="mens")
        self.womens = Category.objects.create(name="Womens", slug="womens")
        brand = Brand.objects.create(name="Comfy Steps")
        style = Style.objects.create(name="Shoes")
        self.black = Color.objects.create(name="Black", hex_code="#000000")
        self.tan = Color.objects.create(name="Tan", hex_code="#C49A6C")
        self.shoe = Product.objects.create(
            category=self.mens, brand=brand, style=style, name="Harlan Mens Tan Boat Shoe",
            price=Decimal("2799"), image=SimpleUploadedFile("a.gif", GIF, content_type="image/gif"), rating=5,
        )
        self.cheap = Product.objects.create(
            category=self.womens, style=style, name="Budget Flip Flop", price=Decimal("499"),
            image=SimpleUploadedFile("b.gif", GIF, content_type="image/gif"),
        )
        self.v41 = ProductVariant.objects.create(product=self.shoe, color=self.tan, size="41", stock=3)
        self.v42 = ProductVariant.objects.create(product=self.shoe, color=self.tan, size="42", stock=0)
        self.flip = ProductVariant.objects.create(product=self.cheap, color=self.black, size="38", stock=10)

    # ---------- helpers ----------
    def register(self, email="nivetha@example.com", password="Str0ng!Pass#2026"):
        res = self.client.post("/api/auth/register/", {
            "email": email, "password": password, "first_name": "Nivetha", "accept_terms": True,
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data["token"]

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def checkout_payload(self, **overrides):
        data = {"first_name": "Nivetha", "last_name": "S", "email": "nivetha@example.com", "phone": "9876543210",
                "address_line1": "2/38 Main Road", "city": "Tenkasi", "state": "Tamil Nadu", "landmark": "",
                "pincode": "627811", "payment_method": "cod"}
        data.update(overrides)
        return data

    # ---------- auth ----------
    def test_register_requires_terms_and_strong_password(self):
        res = self.client.post("/api/auth/register/", {"email": "a@b.com", "password": "123",
                                                       "accept_terms": False}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", str(res.data).lower())
        self.assertIn("accept_terms", res.data)

    def test_login_logout_and_me(self):
        self.register()
        self.client.credentials()
        bad = self.client.post("/api/auth/login/", {"email": "nivetha@example.com", "password": "wrong"}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post("/api/auth/login/", {"email": "NIVETHA@example.com", "password": "Str0ng!Pass#2026"},
                              format="json")
        self.assertEqual(ok.status_code, 200)
        self.auth(ok.data["token"])
        self.assertEqual(self.client.get("/api/auth/me/").data["email"], "nivetha@example.com")
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_password_is_hashed(self):
        self.register()
        user = User.objects.get(email="nivetha@example.com")
        self.assertNotEqual(user.password, "Str0ng!Pass#2026")
        self.assertTrue(user.password.startswith(("pbkdf2_", "argon2", "bcrypt")))

    # ---------- catalogue ----------
    def test_product_list_filters_search_and_sort(self):
        res = self.client.get("/api/products/?category=mens")
        self.assertEqual(res.data["count"], 1)
        res = self.client.get("/api/products/?q=flip")
        self.assertEqual([p["name"] for p in res.data["results"]], ["Budget Flip Flop"])
        res = self.client.get("/api/products/?sort=price_asc")
        self.assertEqual(res.data["results"][0]["name"], "Budget Flip Flop")
        res = self.client.get("/api/products/?size=42")  # size 42 has zero stock
        self.assertEqual(res.data["count"], 0)
        res = self.client.get("/api/products/?color=Tan")
        self.assertEqual(res.data["count"], 1)

    def test_draft_products_are_hidden(self):
        self.cheap.status = Product.STATUS_DRAFT
        self.cheap.save()
        self.assertEqual(self.client.get("/api/products/").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/products/{self.cheap.pk}/").status_code, 404)

    def test_product_detail_by_id_and_slug(self):
        a = self.client.get(f"/api/products/{self.shoe.pk}/")
        b = self.client.get(f"/api/products/{self.shoe.slug}/")
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.data["id"], b.data["id"])
        self.assertEqual(a.data["sizes"], ["41", "42"])

    # ---------- cart ----------
    def test_guest_cart_and_stock_validation(self):
        res = self.client.post("/api/cart/items/", {"variant": self.v41.pk, "quantity": 2}, format="json")
        self.assertEqual(res.status_code, 201)
        token = res.data["token"]
        self.assertTrue(token)
        # Too many for stock (3 available)
        res = self.client.post("/api/cart/items/", {"variant": self.v41.pk, "quantity": 2}, format="json",
                               HTTP_X_CART_TOKEN=token)
        self.assertEqual(res.status_code, 400)
        # Out of stock size
        res = self.client.post("/api/cart/items/", {"variant": self.v42.pk}, format="json", HTTP_X_CART_TOKEN=token)
        self.assertEqual(res.status_code, 400)
        cart = self.client.get("/api/cart/", HTTP_X_CART_TOKEN=token).data
        self.assertEqual(cart["count"], 2)
        self.assertEqual(cart["subtotal"], "5598.00")
        self.assertEqual(cart["shipping"], "0.00")

    def test_guest_cart_merges_on_login(self):
        res = self.client.post("/api/cart/items/", {"variant": self.flip.pk, "quantity": 1}, format="json")
        token = res.data["token"]
        reg = self.client.post("/api/auth/register/", {
            "email": "x@example.com", "password": "Str0ng!Pass#2026", "accept_terms": True,
        }, format="json", HTTP_X_CART_TOKEN=token)
        self.auth(reg.data["token"])
        cart = self.client.get("/api/cart/").data
        self.assertEqual(cart["count"], 1)
        self.assertEqual(cart["shipping"], "99.00")  # below the free-shipping threshold

    def test_update_and_remove_cart_item(self):
        token = self.client.post("/api/cart/items/", {"variant": self.v41.pk}, format="json").data["token"]
        item_id = self.client.get("/api/cart/", HTTP_X_CART_TOKEN=token).data["items"][0]["id"]
        res = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 3}, format="json", HTTP_X_CART_TOKEN=token)
        self.assertEqual(res.data["count"], 3)
        res = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 4}, format="json", HTTP_X_CART_TOKEN=token)
        self.assertEqual(res.status_code, 400)
        res = self.client.delete(f"/api/cart/items/{item_id}/", HTTP_X_CART_TOKEN=token)
        self.assertEqual(res.data["count"], 0)

    # ---------- checkout ----------
    def test_checkout_requires_login(self):
        self.assertEqual(self.client.post("/api/orders/", self.checkout_payload(), format="json").status_code, 401)

    def test_checkout_creates_order_reduces_stock_and_ignores_client_prices(self):
        self.auth(self.register())
        self.client.post("/api/cart/items/", {"variant": self.v41.pk, "quantity": 2}, format="json")
        res = self.client.post("/api/orders/", self.checkout_payload(total="1.00", subtotal="1.00"),
                               format="json", HTTP_X_IDEMPOTENCY_KEY="abc-123")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["total"], "5598.00")
        self.assertTrue(res.data["order_number"].startswith("SU"))
        self.assertEqual(res.data["history"][0]["status"], "placed")
        self.v41.refresh_from_db()
        self.assertEqual(self.v41.stock, 1)
        self.assertEqual(self.client.get("/api/cart/").data["count"], 0)
        # Same idempotency key → same order, no duplicate
        again = self.client.post("/api/orders/", self.checkout_payload(), format="json",
                                 HTTP_X_IDEMPOTENCY_KEY="abc-123")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["id"], res.data["id"])
        self.assertEqual(Order.objects.count(), 1)

    def test_demo_payment_marks_paid_without_card_data(self):
        self.auth(self.register())
        self.client.post("/api/cart/items/", {"variant": self.flip.pk}, format="json")
        res = self.client.post("/api/orders/", self.checkout_payload(payment_method="demo_online",
                                                                     card_number="4111111111111111"), format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["payment_status"], "paid")
        self.assertTrue(res.data["transaction_reference"].startswith("DEMO-"))
        self.assertNotIn("4111", str(Order.objects.get().__dict__))

    def place_razorpay_order(self):
        self.auth(self.register())
        self.client.post("/api/cart/items/", {"variant": self.flip.pk}, format="json")
        res = self.client.post("/api/orders/", self.checkout_payload(payment_method="razorpay"), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def test_razorpay_rejected_when_not_configured(self):
        self.auth(self.register())
        self.client.post("/api/cart/items/", {"variant": self.flip.pk}, format="json")
        res = self.client.post("/api/orders/", self.checkout_payload(payment_method="razorpay"), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertFalse(self.client.get("/api/payments/config/").data["online_enabled"])

    @override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret", RAZORPAY_WEBHOOK_SECRET="whsec")
    def test_razorpay_payment_flow_verifies_signature(self):
        import hashlib
        import hmac
        from unittest import mock

        self.assertTrue(self.client.get("/api/payments/config/").data["online_enabled"])
        order = self.place_razorpay_order()
        self.assertEqual(order["payment_status"], "pending")

        with mock.patch("payments.services._post_order", return_value={"id": "order_ABC"}) as post:
            start = self.client.post("/api/payments/start/", {"order_id": order["id"]}, format="json")
            self.client.post("/api/payments/start/", {"order_id": order["id"]}, format="json")
        self.assertEqual(start.status_code, 200)
        self.assertEqual(post.call_count, 1)  # the gateway order is reused on retry
        self.assertEqual(start.data["gateway_order_id"], "order_ABC")
        self.assertEqual(start.data["amount"], int(Decimal(order["total"]) * 100))

        forged = {"order_id": order["id"], "razorpay_order_id": "order_ABC", "razorpay_payment_id": "pay_1",
                  "razorpay_signature": "0" * 64}
        self.assertEqual(self.client.post("/api/payments/verify/", forged, format="json").status_code, 400)
        self.assertEqual(Order.objects.get().payment_status, "pending")

        good = hmac.new(b"secret", b"order_ABC|pay_1", hashlib.sha256).hexdigest()
        ok = self.client.post("/api/payments/verify/", {**forged, "razorpay_signature": good}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["payment_status"], "paid")
        self.assertEqual(ok.data["transaction_reference"], "pay_1")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret", RAZORPAY_WEBHOOK_SECRET="whsec")
    def test_razorpay_webhook_marks_paid_and_rejects_bad_signature(self):
        import hashlib
        import hmac
        import json
        from unittest import mock

        order = self.place_razorpay_order()
        with mock.patch("payments.services._post_order", return_value={"id": "order_WH"}):
            self.client.post("/api/payments/start/", {"order_id": order["id"]}, format="json")
        body = json.dumps({"event": "payment.captured",
                           "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_WH"}}}})
        self.client.credentials()  # the webhook is called by Razorpay, not a logged-in customer
        bad = self.client.post("/api/payments/webhook/", body, content_type="application/json",
                               HTTP_X_RAZORPAY_SIGNATURE="nope")
        self.assertEqual(bad.status_code, 400)
        sig = hmac.new(b"whsec", body.encode(), hashlib.sha256).hexdigest()
        good = self.client.post("/api/payments/webhook/", body, content_type="application/json",
                                HTTP_X_RAZORPAY_SIGNATURE=sig)
        self.assertEqual(good.status_code, 200)
        self.assertEqual(Order.objects.get().payment_status, "paid")

    def test_checkout_validation_errors(self):
        self.auth(self.register())
        self.client.post("/api/cart/items/", {"variant": self.flip.pk}, format="json")
        res = self.client.post("/api/orders/", self.checkout_payload(pincode="12", phone="abc"), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("pincode", res.data)
        self.assertIn("phone", res.data)

    def test_empty_cart_and_stock_race(self):
        self.auth(self.register())
        self.assertEqual(self.client.post("/api/orders/", self.checkout_payload(), format="json").status_code, 400)
        self.client.post("/api/cart/items/", {"variant": self.v41.pk, "quantity": 3}, format="json")
        ProductVariant.objects.filter(pk=self.v41.pk).update(stock=1)  # someone else bought them
        res = self.client.post("/api/orders/", self.checkout_payload(), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("only 1 left", str(res.data))

    def test_cancel_restocks(self):
        self.auth(self.register())
        self.client.post("/api/cart/items/", {"variant": self.v41.pk, "quantity": 2}, format="json")
        order_id = self.client.post("/api/orders/", self.checkout_payload(), format="json").data["id"]
        res = self.client.post(f"/api/orders/{order_id}/cancel/")
        self.assertEqual(res.data["status"], "cancelled")
        self.v41.refresh_from_db()
        self.assertEqual(self.v41.stock, 3)
        self.assertEqual(self.client.post(f"/api/orders/{order_id}/cancel/").status_code, 400)

    # ---------- privacy ----------
    def test_customers_cannot_see_each_others_orders_or_addresses(self):
        self.auth(self.register("one@example.com"))
        self.client.post("/api/cart/items/", {"variant": self.flip.pk}, format="json")
        order_id = self.client.post("/api/orders/", self.checkout_payload(save_address=True), format="json").data["id"]
        addr_id = self.client.get("/api/addresses/").data[0]["id"]

        self.auth(self.register("two@example.com"))
        self.assertEqual(self.client.get(f"/api/orders/{order_id}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/orders/{order_id}/cancel/").status_code, 404)
        self.assertEqual(self.client.get("/api/orders/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/addresses/{addr_id}/").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/addresses/{addr_id}/").status_code, 404)

    # ---------- wishlist / reviews / misc ----------
    def test_wishlist(self):
        self.assertEqual(self.client.get("/api/wishlist/").status_code, 401)
        self.auth(self.register())
        self.assertEqual(self.client.post("/api/wishlist/", {"product_id": self.shoe.pk}, format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/wishlist/", {"product_id": self.shoe.pk}, format="json").status_code, 200)
        self.assertEqual(len(self.client.get("/api/wishlist/").data), 1)
        self.assertEqual(self.client.delete(f"/api/wishlist/{self.shoe.pk}/").status_code, 204)

    def test_review_updates_rating(self):
        self.auth(self.register())
        payload = {"title": "Super Looking", "rating": 3, "fit": 4, "comfort": 4, "value_for_money": 3,
                   "quality": 4, "comment": "Nice", "recommend": True}
        self.assertEqual(self.client.post(f"/api/products/{self.shoe.pk}/reviews/", payload, format="json").status_code, 201)
        self.shoe.refresh_from_db()
        self.assertEqual(self.shoe.rating, Decimal("3.0"))
        self.assertEqual(self.client.post(f"/api/products/{self.shoe.pk}/reviews/", payload, format="json").status_code, 400)

    def test_contact_and_newsletter(self):
        self.assertEqual(self.client.post("/api/contact/", {"name": "A", "email": "a@b.com", "message": "Hi"},
                                          format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/newsletter/", {"email": "bad"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/newsletter/", {"email": "a@b.com"}, format="json").status_code, 201)

    def test_admin_requires_staff(self):
        res = self.client.get("/admin/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/admin/login/", res["Location"])
