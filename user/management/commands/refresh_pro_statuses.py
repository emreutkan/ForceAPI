from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


User = get_user_model()


class Command(BaseCommand):
    help = "Disable expired paid PRO subscriptions based on pro_until."

    def handle(self, *args, **options):
        now = timezone.now()
        expired_users = list(
            User.objects.filter(is_pro=True, pro_until__isnull=False, pro_until__lt=now).only("id", "email")
        )

        if not expired_users:
            self.stdout.write("No expired PRO users found.")
            return

        expired_ids = [user.id for user in expired_users]

        with transaction.atomic():
            updated_count = User.objects.filter(id__in=expired_ids).update(is_pro=False)

        self.stdout.write(self.style.SUCCESS(f"Refreshed {updated_count} expired PRO user(s)."))
        for user in expired_users:
            self.stdout.write(f" - {user.email}")
