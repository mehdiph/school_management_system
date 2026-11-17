"""
Re-encrypts every personal access row with the newest key in
``ONLINE_ACCESS_KEYS``, so that an old key can then be removed (D14; the steps
are in ``docs/apps/online_classes.md``).

    python manage.py reencrypt_online_access            # dry run: reports only
    python manage.py reencrypt_online_access --apply    # writes

It prints counts and row ids, never a value. It doesn't touch ``updated_by`` or
``updated_at``: this is not an edit anyone made. A row no configured key opens
is left as it is and the command fails, so nobody removes a key still needed.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from online_classes import crypto
from online_classes.models import OnlineEventAccess
from online_classes.models.access import SECRET_FIELDS

BATCH_SIZE = 200


class Command(BaseCommand):
    help = "Re-encrypts personal access rows with the newest key (dry run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write the changes; without it, only report")

    def handle(self, *args, **options):
        apply = options["apply"]
        ids = list(OnlineEventAccess.objects.order_by("pk").values_list("pk", flat=True))
        rewritten, current, failed = 0, 0, []

        for start in range(0, len(ids), BATCH_SIZE):
            with transaction.atomic():
                rows = OnlineEventAccess.objects.select_for_update().filter(pk__in=ids[start:start + BATCH_SIZE])
                changed = []
                for row in rows:
                    if all(crypto.uses_newest_key(getattr(row, name)) for name in SECRET_FIELDS):
                        current += 1
                        continue
                    try:
                        for name in SECRET_FIELDS:
                            setattr(row, name, crypto.reencrypt(getattr(row, name)))
                    except crypto.DecryptionFailed:
                        failed.append(row.pk)
                        continue
                    rewritten += 1
                    changed.append(row)
                if apply and changed:
                    OnlineEventAccess.objects.bulk_update(changed, SECRET_FIELDS)

        verb = "rewritten" if apply else "would be rewritten"
        self.stdout.write(f"rows={len(ids)} {verb}={rewritten} already_on_newest_key={current} unreadable={len(failed)}")
        if not apply:
            self.stdout.write("Dry run: nothing was written. Run again with --apply.")

        if failed:
            raise CommandError(
                "No configured key opens these rows, so they were left as they are: "
                + ", ".join(str(pk) for pk in failed)
                + ". Do not remove any key until they are fixed: restore the missing key, or enter them again."
            )
        if apply:
            self.stdout.write(self.style.SUCCESS("Every row is on the newest key; older keys can now be removed."))
