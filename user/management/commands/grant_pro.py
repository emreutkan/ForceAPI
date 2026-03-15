from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


User = get_user_model()


class Command(BaseCommand):
    help = "Grant, revoke, or make PRO permanent for a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            help="User email to update.",
        )
        parser.add_argument(
            "--user-id",
            type=str,
            help="User UUID to update.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to grant PRO for (default: 30).",
        )
        parser.add_argument(
            "--permanent",
            action="store_true",
            help="Grant PRO with no expiration date.",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Revoke PRO instead of granting it.",
        )

    def handle(self, *args, **options):
        email = options.get("email")
        user_id = options.get("user_id")
        days = options.get("days")
        permanent = options.get("permanent")
        revoke = options.get("revoke")

        if not email and not user_id:
            raise CommandError("Provide either --email or --user-id.")

        if email and user_id:
            raise CommandError("Use only one lookup: --email or --user-id.")

        if days <= 0 and not revoke:
            raise CommandError("--days must be greater than 0 unless --revoke is used.")

        if permanent and revoke:
            raise CommandError("--permanent cannot be combined with --revoke.")

        filters = {"email": email} if email else {"id": user_id}

        try:
            user = User.objects.get(**filters)
        except User.DoesNotExist as exc:
            lookup_value = email or user_id
            raise CommandError(f"User not found: {lookup_value}") from exc

        if revoke:
            user.is_pro = False
            user.pro_until = None
            user.subscription_id = ""
            user.save(update_fields=["is_pro", "pro_until", "subscription_id", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"Revoked PRO for {user.email}"))
            return

        user.is_pro = True
        user.pro_until = None if permanent else timezone.now() + timedelta(days=days)
        user.save(update_fields=["is_pro", "pro_until", "updated_at"])

        if permanent:
            self.stdout.write(self.style.SUCCESS(f"Granted permanent PRO to {user.email}"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Granted PRO to {user.email} until {user.pro_until.isoformat()}"
                )
            )
