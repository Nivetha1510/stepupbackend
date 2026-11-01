"""Password-reset security tests."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import GoogleAccount

User = get_user_model()
OLD = "Str0ng!Pass#2026"
NEW = "Brand#New!Pass7731"
GENERIC = "If an eligible account exists, a password reset link has been sent."


class PasswordResetSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()  # throttle counters and email cooldowns live in the cache
        self.user = User.objects.create_user(username="nivetha@example.com", email="nivetha@example.com", password=OLD)

    def credentials(self, user=None):
        user = user or self.user
        return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)

    def reset(self, uid, token, password=NEW, confirm=None):
        return self.client.post("/api/auth/reset-password/", {
            "uid": uid, "token": token, "password": password,
            "confirm_password": password if confirm is None else confirm}, format="json")

    def test_forgot_password_response_is_identical_for_all_accounts(self):
        google = User.objects.create(username="google_abc", email="g@example.com")
        google.set_unusable_password()
        google.save()
        GoogleAccount.objects.create(user=google, google_sub="sub-1")

        responses = [self.client.post("/api/auth/forgot-password/", {"email": e}, format="json")
                     for e in ("nivetha@example.com", "nobody@example.com", "g@example.com")]
        for res in responses:
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data, {"detail": GENERIC})
        # Only the password account received an email; the Google-only account got none.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["nivetha@example.com"])

    def test_forgot_password_does_not_fail_or_leak_when_mail_sending_breaks(self):
        with mock.patch("accounts.views.send_mail", side_effect=OSError("smtp down")):
            res = self.client.post("/api/auth/forgot-password/", {"email": "nivetha@example.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, {"detail": GENERIC})

    def test_reset_email_cooldown_per_address(self):
        for _ in range(2):
            self.client.post("/api/auth/forgot-password/", {"email": "nivetha@example.com"}, format="json")
        self.assertEqual(len(mail.outbox), 1)

    def test_forgot_password_is_rate_limited_per_ip(self):
        statuses = [self.client.post("/api/auth/forgot-password/", {"email": f"u{i}@example.com"}, format="json").status_code
                    for i in range(7)]
        self.assertEqual(statuses[:5], [200] * 5)
        self.assertIn(429, statuses[5:])

    def test_valid_link_resets_password_hashed_and_revokes_api_tokens(self):
        Token.objects.create(user=self.user)
        uid, token = self.credentials()
        res = self.reset(uid, token)
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertTrue(self.user.password.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")))
        self.assertNotIn(NEW, self.user.password)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.post("/api/auth/login/", {"email": "nivetha@example.com", "password": OLD},
                                          format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login/", {"email": "nivetha@example.com", "password": NEW},
                                          format="json").status_code, 200)

    def test_link_cannot_be_reused(self):
        uid, token = self.credentials()
        self.assertEqual(self.reset(uid, token).status_code, 200)
        again = self.reset(uid, token, password="An0ther!Pass#8842")
        self.assertEqual(again.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_link_is_rejected(self):
        uid, token = self.credentials()
        self.assertEqual(self.reset(uid, token).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_invalid_tampered_and_foreign_links_are_rejected(self):
        uid, token = self.credentials()
        other = User.objects.create_user(username="o@example.com", email="o@example.com", password=OLD)
        other_uid, _ = self.credentials(other)
        for bad_uid, bad_token in [(uid, token[:-1] + ("a" if token[-1] != "a" else "b")), (uid, "garbage"),
                                   (other_uid, token), ("!!", token), (uid, "x" * 500)]:
            res = self.reset(bad_uid, bad_token)
            self.assertEqual(res.status_code, 400, (bad_uid, bad_token))
            self.assertEqual(res.data["detail"], "Invalid or expired reset link.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_django_password_validation_is_enforced(self):
        uid, token = self.credentials()
        for weak in ("short1!", "password", "12345678901", "nivetha@example.com"):
            res = self.reset(uid, token, password=weak)
            self.assertEqual(res.status_code, 400, weak)
            self.assertIn("password", res.data)
        self.assertEqual(self.reset(uid, token, password=NEW, confirm="Different#Pass9").status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))  # a failed attempt must not burn or change anything
        self.assertEqual(self.reset(uid, token).status_code, 200)

    def test_google_only_account_cannot_be_reset(self):
        google = User.objects.create(username="google_xyz", email="g2@example.com")
        google.set_unusable_password()
        google.save()
        uid, token = self.credentials(google)
        self.assertEqual(self.reset(uid, token).status_code, 400)
        google.refresh_from_db()
        self.assertFalse(google.has_usable_password())

    def test_inactive_account_cannot_be_reset(self):
        uid, token = self.credentials()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.reset(uid, token).status_code, 400)

    def test_reset_submission_is_rate_limited(self):
        uid, _ = self.credentials()
        statuses = [self.reset(uid, "bad-token").status_code for _ in range(12)]
        self.assertEqual(statuses[:10], [400] * 10)
        self.assertEqual(statuses[10], 429)

    def test_reset_link_and_password_are_not_logged(self):
        with self.assertLogs(level="DEBUG") as logs, mock.patch("accounts.views.send_mail", side_effect=OSError("x")):
            self.client.post("/api/auth/forgot-password/", {"email": "nivetha@example.com"}, format="json")
            uid, token = self.credentials()
            self.reset(uid, token, password=NEW)
            self.reset(uid, token, password=NEW)
        text = "\n".join(logs.output)
        for secret in (token, NEW, "reset-password?"):
            self.assertNotIn(secret, text)


class ResetEmailContentTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="nivetha@example.com", email="nivetha@example.com", password=OLD)

    @override_settings(FRONTEND_URL="https://shop.example.com/", DEFAULT_FROM_EMAIL="StepUp Support <help@shop.example.com>")
    def test_email_uses_configured_sender_and_frontend_url(self):
        self.client.post("/api/auth/forgot-password/", {"email": "NIVETHA@example.com "}, format="json")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.from_email, "StepUp Support <help@shop.example.com>")
        self.assertEqual(message.to, ["nivetha@example.com"])
        link = next(line for line in message.body.splitlines() if "reset-password?" in line)
        self.assertTrue(link.startswith("https://shop.example.com/reset-password?uid="), link)
        # The emailed link really resets the password.
        from urllib.parse import parse_qs, urlparse
        query = parse_qs(urlparse(link).query)
        res = self.client.post("/api/auth/reset-password/", {
            "uid": query["uid"][0], "token": query["token"][0], "password": NEW, "confirm_password": NEW}, format="json")
        self.assertEqual(res.status_code, 200)


@override_settings(GOOGLE_CLIENT_ID="test-client-id")
class GoogleSignInStillWorksTests(APITestCase):
    def setUp(self):
        cache.clear()

    def sign_in(self, email="g@example.com", sub="sub-123"):
        payload = {"sub": sub, "email": email, "email_verified": True}
        with mock.patch("accounts.views.id_token.verify_oauth2_token", return_value=payload):
            return self.client.post("/api/auth/google/", {"credential": "fake"}, format="json")

    def test_google_signup_and_return_login(self):
        first = self.sign_in()
        self.assertEqual(first.status_code, 200, first.data)
        self.assertIn("token", first.data)
        user = User.objects.get(email="g@example.com")
        self.assertFalse(user.has_usable_password())
        again = self.sign_in()
        self.assertEqual(again.status_code, 200)
        self.assertEqual(User.objects.filter(email="g@example.com").count(), 1)

    def test_google_does_not_take_over_a_password_account(self):
        User.objects.create_user(username="p@example.com", email="p@example.com", password=OLD)
        res = self.sign_in(email="p@example.com", sub="sub-999")
        self.assertEqual(res.status_code, 409)

    def test_registration_and_login_still_work(self):
        reg = self.client.post("/api/auth/register/", {"email": "new@example.com", "password": OLD, "first_name": "N",
                                                       "accept_terms": True}, format="json")
        self.assertEqual(reg.status_code, 201, reg.data)
        login = self.client.post("/api/auth/login/", {"email": "new@example.com", "password": OLD}, format="json")
        self.assertEqual(login.status_code, 200)
        self.assertIn("token", login.data)
