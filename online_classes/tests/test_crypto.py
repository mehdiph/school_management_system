from io import StringIO

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings

from online_classes import crypto
from online_classes.models import OnlineEvent, OnlineEventAccess
from online_classes.testing import SchoolMixin, make_access, make_event

OLD_KEY = Fernet.generate_key().decode()
NEW_KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()


class CryptoTests(TestCase):
    def test_round_trip_and_ciphertext(self):
        token = crypto.encrypt("رمز-۱۲۳")
        self.assertNotIn("رمز", token)
        self.assertEqual(crypto.decrypt(token), "رمز-۱۲۳")

    def test_empty_stays_empty(self):
        self.assertEqual(crypto.encrypt(""), "")
        self.assertEqual(crypto.decrypt(""), "")

    def test_wrong_key_is_a_clear_failure(self):
        with override_settings(ONLINE_ACCESS_KEYS=[OLD_KEY]):
            token = crypto.encrypt("x")
        with override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY]), self.assertRaises(crypto.DecryptionFailed):
            crypto.decrypt(token)

    def test_garbage_is_a_clear_failure(self):
        with self.assertRaises(crypto.DecryptionFailed):
            crypto.decrypt("not-a-token")

    def test_rotation_reads_old_and_writes_new(self):
        with override_settings(ONLINE_ACCESS_KEYS=[OLD_KEY]):
            token = crypto.encrypt("x")
        with override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY, OLD_KEY]):
            self.assertEqual(crypto.decrypt(token), "x")
            self.assertFalse(crypto.uses_newest_key(token))
            rotated = crypto.reencrypt(token)
            self.assertTrue(crypto.uses_newest_key(rotated))
        with override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY]):
            self.assertEqual(crypto.decrypt(rotated), "x")

    def test_no_keys_is_a_configuration_error(self):
        with override_settings(ONLINE_ACCESS_KEYS=[]), self.assertRaises(ImproperlyConfigured):
            crypto.encrypt("x")


class StoredRowTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.event = make_event(access_mode=OnlineEvent.AccessMode.PERSONAL)

    def test_the_database_holds_only_ciphertext(self):
        row = make_access(
            self.event, self.student_a1, url="https://example.com/secret-link", password="pw-plain", access_code="code-plain"
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT url_encrypted, password_encrypted, access_code_encrypted FROM online_classes_onlineeventaccess"
                " WHERE id = %s",
                [row.pk],
            )
            stored = " ".join(cursor.fetchone())
        for plain in ("secret-link", "pw-plain", "code-plain"):
            self.assertNotIn(plain, stored)
        self.assertNotIn("pw-plain", str(row))
        self.assertEqual(
            OnlineEventAccess.objects.get(pk=row.pk).read_secrets(),
            {"url": "https://example.com/secret-link", "password": "pw-plain", "access_code": "code-plain"},
        )

    def test_blank_keeps_what_is_stored(self):
        row = make_access(self.event, self.student_a1, password="first", url="https://example.com/a")
        row.set_secrets(password="", url=None, access_code="new-code")
        row.save()
        self.assertEqual(
            OnlineEventAccess.objects.get(pk=row.pk).read_secrets(),
            {"url": "https://example.com/a", "password": "first", "access_code": "new-code"},
        )


class ReencryptCommandTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.event = make_event(access_mode=OnlineEvent.AccessMode.PERSONAL)
        with override_settings(ONLINE_ACCESS_KEYS=[OLD_KEY]):
            self.row = make_access(self.event, self.student_a1, password="pw-plain", url="https://example.com/plain-link")
            self.row_b = make_access(self.event, self.student_b1, username="only-username")

    def _run(self, *args):
        out = StringIO()
        call_command("reencrypt_online_access", *args, stdout=out)
        return out.getvalue()

    def _stored(self):
        return OnlineEventAccess.objects.values_list("password_encrypted", "url_encrypted").get(pk=self.row.pk)

    @override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY, OLD_KEY])
    def test_dry_run_is_the_default_and_writes_nothing(self):
        before = self._stored()
        output = self._run()
        self.assertEqual(self._stored(), before)
        self.assertIn("would be rewritten=1", output)
        self.assertIn("already_on_newest_key=1", output)
        self.assertIn("Dry run", output)

    def test_apply_lets_the_old_key_go(self):
        row = OnlineEventAccess.objects.get(pk=self.row.pk)
        updated_at, updated_by = row.updated_at, row.updated_by_id

        with override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY, OLD_KEY]):
            output = self._run("--apply")
            self.assertIn("rewritten=1", output)
            self.assertIn("older keys can now be removed", output)
            self.assertIn("rewritten=0", self._run("--apply"), "a second run has nothing to do")

        with override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY]):
            row = OnlineEventAccess.objects.get(pk=self.row.pk)
            self.assertEqual(row.read_secrets()["password"], "pw-plain")
            self.assertEqual(row.read_secrets()["url"], "https://example.com/plain-link")
            self.assertEqual(row.updated_at, updated_at)
            self.assertEqual(row.updated_by_id, updated_by)

    def test_no_value_is_ever_printed(self):
        with override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY, OLD_KEY]):
            output = self._run("--apply")
        for value in ("pw-plain", "plain-link", "only-username", self._stored()[0]):
            self.assertNotIn(value, output)

    def test_an_unreadable_row_fails_and_stays_as_it_is(self):
        with override_settings(ONLINE_ACCESS_KEYS=[OTHER_KEY]):
            lost = make_access(self.event, self.student_a2, password="lost-pw")
        before = OnlineEventAccess.objects.values_list("password_encrypted", flat=True).get(pk=lost.pk)

        out = StringIO()
        with override_settings(ONLINE_ACCESS_KEYS=[NEW_KEY, OLD_KEY]):
            with self.assertRaises(CommandError) as caught:
                call_command("reencrypt_online_access", "--apply", stdout=out)

        self.assertIn(str(lost.pk), str(caught.exception))
        self.assertNotIn("older keys can now be removed", out.getvalue())
        self.assertEqual(OnlineEventAccess.objects.values_list("password_encrypted", flat=True).get(pk=lost.pk), before)
        # The readable rows were still moved to the newest key.
        self.assertIn("rewritten=1", out.getvalue())
