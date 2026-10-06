"""
Teacher profile & settings (/auth/profile/): access, personal details
(mobile, email, avatar), password change, sign-in history and signing
out of other devices.
"""

import io
import shutil
import tempfile

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.testing import make_student, make_teacher_profile, make_user

from .models import LoginActivity, User
from .sessions import client_ip, describe_user_agent
from .validators import normalize_mobile

PASSWORD = "test-pass-123"
URL = reverse("accounts:profile")
CHROME_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"
)

FAST_HASHER = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


def image_file(name="me.jpg", fmt="JPEG", size=(600, 400), exif_orientation=None, color=(200, 80, 40)):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation          # Orientation
        exif[0x8825] = {1: "N", 2: (35.0, 41.0, 0.0)}  # GPSInfo
        kwargs["exif"] = exif
    image.save(buffer, format=fmt, **kwargs)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class MobileNormalizationTests(SimpleTestCase):

    def test_persian_digits_country_code_and_separators(self):
        for raw in ("۰۹۱۲ ۳۴۵ ۶۷۸۹", "+98 912-345-6789", "00989123456789", "٠٩١٢٣٤٥٦٧٨٩", "9123456789"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_mobile(raw), "09123456789")


class ClientIpTests(SimpleTestCase):

    def request(self, **meta):
        from django.test import RequestFactory

        return RequestFactory().get("/", **meta)

    def test_forwarded_for_is_never_trusted(self):
        request = self.request(REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="6.6.6.6")
        self.assertEqual(client_ip(request), "10.0.0.2")

    @override_settings(CLIENT_IP_HEADER="HTTP_X_REAL_IP")
    def test_configured_proxy_header(self):
        request = self.request(REMOTE_ADDR="172.18.0.5", HTTP_X_REAL_IP="5.6.7.8")
        self.assertEqual(client_ip(request), "5.6.7.8")

    def test_user_agent_is_described_plainly(self):
        self.assertEqual(describe_user_agent(CHROME_ANDROID), ("Chrome 128", "Android"))


@FAST_HASHER
class ProfileAccessTests(TestCase):

    def test_anonymous_is_sent_to_login(self):
        self.assertRedirects(self.client.get(URL), f"{reverse('accounts:login')}?next={URL}", fetch_redirect_response=False)

    def test_student_is_sent_to_their_own_dashboard(self):
        self.client.force_login(make_student().user)
        self.assertRedirects(self.client.get(URL), reverse("student:dashboard"), fetch_redirect_response=False)

    def test_teacher_sees_both_tabs_and_admin_managed_fields_read_only(self):
        teacher = make_teacher_profile()
        self.client.force_login(teacher.staff.user)

        response = self.client.get(URL + "?tab=security")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tab"], "security")
        self.assertContains(response, "برای تغییر، با مدیر سامانه تماس بگیرید")
        self.assertContains(response, f'value="{teacher.staff.user.username}" dir="ltr" readonly')


@FAST_HASHER
class PersonalDetailsTests(TestCase):

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

        self.user = make_teacher_profile().staff.user
        self.client.force_login(self.user)

    def post(self, **data):
        payload = {"action": "personal", "phone_number": "09121112233", "email": ""}
        payload.update(data)
        return self.client.post(URL, payload)

    def test_mobile_is_normalized_and_saved(self):
        response = self.post(phone_number="+98 912 ۱۲۳ ۴۵۶۷", email="Teacher@Example.com")

        self.assertRedirects(response, URL + "?tab=personal", fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual((self.user.phone_number, self.user.email), ("09121234567", "teacher@example.com"))

    def test_invalid_mobile_is_rejected_in_persian_on_the_personal_tab(self):
        response = self.post(phone_number="0212345678")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tab"], "personal")
        self.assertFormError(
            response.context["profile_form"], "phone_number",
            "شماره موبایل باید ۱۱ رقم باشد و با ۰۹ شروع شود؛ مثل ۰۹۱۲۳۴۵۶۷۸۹.",
        )
        self.assertContains(response, 'aria-invalid="true"')
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09120000000")

    def test_avatar_is_squared_resized_reencoded_and_stripped(self):
        self.post(avatar=image_file(exif_orientation=6))

        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith("users/avatars/"))
        self.assertTrue(self.user.avatar.name.endswith(".jpg"))
        with Image.open(self.user.avatar.path) as saved:
            self.assertEqual((saved.format, saved.size), ("JPEG", (256, 256)))
            self.assertEqual(len(saved.getexif()), 0)  # no orientation, no GPS

    def test_replacing_the_avatar_deletes_the_old_file(self):
        self.post(avatar=image_file())
        self.user.refresh_from_db()
        old_path = self.user.avatar.path

        with self.captureOnCommitCallbacks(execute=True):
            self.post(avatar=image_file("new.png", fmt="PNG"))

        self.user.refresh_from_db()
        self.assertNotEqual(self.user.avatar.path, old_path)
        self.assertFalse(self.user.avatar.storage.exists(old_path))

    def test_remove_avatar(self):
        self.post(avatar=image_file())
        self.user.refresh_from_db()
        path = self.user.avatar.path

        with self.captureOnCommitCallbacks(execute=True):
            self.post(remove_avatar="on")

        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
        self.assertFalse(self.user.avatar.storage.exists(path))

    def test_oversized_avatar_is_rejected(self):
        big = SimpleUploadedFile("big.jpg", b"\xff\xd8" + b"0" * (2 * 1024 * 1024 + 1), content_type="image/jpeg")
        response = self.post(avatar=big)
        self.assertFormError(response.context["profile_form"], "avatar", "حجم تصویر نباید بیشتر از ۲ مگابایت باشد.")

    def test_non_image_is_rejected(self):
        fake = SimpleUploadedFile("photo.jpg", b"not really an image", content_type="image/jpeg")
        response = self.post(avatar=fake)
        self.assertFormError(response.context["profile_form"], "avatar", "این فایل یک تصویر سالم نیست.")

    def test_other_image_types_are_rejected(self):
        response = self.post(avatar=image_file("me.gif", fmt="GIF"))
        self.assertFormError(response.context["profile_form"], "avatar", "فقط تصویر JPG، PNG یا WebP پذیرفته می‌شود.")

    def test_admin_managed_fields_cannot_be_changed(self):
        original = (self.user.username, self.user.first_name, self.user.national_code)
        self.post(username="hacker", first_name="X", national_code="0012345679")
        self.user.refresh_from_db()
        self.assertEqual((self.user.username, self.user.first_name, self.user.national_code), original)


@FAST_HASHER
class SecurityTests(TestCase):

    def setUp(self):
        self.user = make_teacher_profile().staff.user
        self.client.login(username=self.user.username, password=PASSWORD)

    def other_device(self):
        # Through the real login form: Client.login() builds its own
        # request without the client's headers (no user agent).
        other = Client(HTTP_USER_AGENT=CHROME_ANDROID)
        other.post(reverse("accounts:login"), {
            "username": self.user.username, "password": PASSWORD, "role": "teacher",
        })
        assert "_auth_user_id" in other.session
        return other

    def change_password(self, old=PASSWORD, new="Kh0b-va-Taze!", again=None):
        return self.client.post(URL, {
            "action": "password",
            "old_password": old,
            "new_password1": new,
            "new_password2": again or new,
        })

    def test_password_change_keeps_this_session_and_ends_the_others(self):
        other = self.other_device()

        response = self.change_password()

        self.assertRedirects(response, URL + "?tab=security", fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Kh0b-va-Taze!"))
        self.assertEqual(self.client.get(URL).status_code, 200)             # still signed in here
        self.assertEqual(other.get(URL).status_code, 302)                   # signed out there
        current = self.client.session.session_key
        self.assertEqual(
            list(LoginActivity.objects.filter(user=self.user).exclude(session_key=None).values_list("session_key", flat=True)),
            [current],
        )

    def test_wrong_current_password_in_persian(self):
        response = self.change_password(old="nope")
        self.assertEqual(response.context["tab"], "security")
        self.assertFormError(response.context["password_form"], "old_password", "رمز عبور فعلی درست نیست.")

    def test_validator_errors_are_persian(self):
        response = self.change_password(new="1234567")
        errors = response.context["password_form"].errors["new_password2"]
        self.assertIn("رمز عبور باید دست‌کم ۸ نویسه باشد.", errors)
        self.assertIn("رمز عبور نباید فقط از عدد تشکیل شده باشد.", errors)

    def test_mismatch_in_persian(self):
        response = self.change_password(again="something-else-1")
        self.assertFormError(
            response.context["password_form"], "new_password2", "تکرار رمز عبور با رمز عبور جدید یکسان نیست."
        )

    def test_login_is_recorded_and_current_one_marked(self):
        self.other_device()

        response = self.client.get(URL + "?tab=security")

        logins = response.context["logins"]
        self.assertEqual(len(logins), 2)
        self.assertEqual((logins[0].browser, logins[0].os), ("Chrome 128", "Android"))
        self.assertEqual(logins[0].ip_address, "127.0.0.1")
        self.assertContains(response, "ui-badge--success\">همین دستگاه", count=1)
        self.assertEqual(logins[1].session_key, self.client.session.session_key)

    def test_end_other_sessions(self):
        other = self.other_device()
        other_key = other.session.session_key

        response = self.client.post(URL, {"action": "end_sessions"})

        self.assertRedirects(response, URL + "?tab=security", fetch_redirect_response=False)
        self.assertFalse(Session.objects.filter(session_key=other_key).exists())
        self.assertEqual(other.get(URL).status_code, 302)
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_logout_forgets_the_session(self):
        key = self.client.session.session_key
        self.client.get(reverse("accounts:logout"))
        self.assertFalse(LoginActivity.objects.filter(session_key=key).exists())

    def test_history_is_capped_per_user(self):
        from .sessions import KEEP_PER_USER

        for _ in range(KEEP_PER_USER + 3):
            self.client.login(username=self.user.username, password=PASSWORD)
        self.assertEqual(LoginActivity.objects.filter(user=self.user).count(), KEEP_PER_USER)

    def test_forced_password_change_page_keeps_tracking_current(self):
        self.user.must_change_password = True
        self.user.save()
        self.client.post(reverse("accounts:password_change"), {
            "old_password": PASSWORD, "new_password1": "Kh0b-va-Taze!", "new_password2": "Kh0b-va-Taze!",
        })
        current = self.client.session.session_key
        self.assertTrue(LoginActivity.objects.filter(user=self.user, session_key=current).exists())
