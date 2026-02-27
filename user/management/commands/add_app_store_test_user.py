"""
Creates or updates an App Store test user for TestFlight / App Review.
Fills the account with test data: profile, weight history, body measurements, and sample workouts.
Use the same credentials in App Store Connect > Users and Access > Sandbox testers,
and for signing in from the app when using Sandbox environment.
"""
import random
import requests
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from user.models import CustomUser, UserProfile, WeightHistory
from body_measurements.models import BodyMeasurement
from exercise.models import Exercise
from workout.models import Workout, WorkoutExercise, ExerciseSet, WorkoutProgram, WorkoutProgramDay, WorkoutProgramExercise


# Credentials for App Store / TestFlight testing (document in App Store Connect sandbox testers)
APP_STORE_TEST_EMAIL = "appstore.test@force.test"
APP_STORE_TEST_PASSWORD = "TestUser123!"

# Test data constants
TEST_HEIGHT = Decimal("175.0")
TEST_WEIGHT = Decimal("75.0")


class Command(BaseCommand):
    help = "Creates or updates the App Store test user for TestFlight and App Review, with sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default=APP_STORE_TEST_EMAIL,
            help=f"Test user email (default: {APP_STORE_TEST_EMAIL})",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=APP_STORE_TEST_PASSWORD,
            help="Test user password (default: TestUser123!)",
        )
        parser.add_argument(
            "--pro",
            action="store_true",
            help="Grant PRO subscription (30 days from now) for testing premium features.",
        )
        parser.add_argument(
            "--no-data",
            action="store_true",
            help="Skip adding weight history, body measurements, and workouts.",
        )

    def handle(self, *args, **options):
        email = options["email"]
        password = options["password"]
        grant_pro = options["pro"]
        skip_data = options["no_data"]

        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                "first_name": "App Store",
                "last_name": "Tester",
                "is_verified": True,
                "gender": "male",
                "is_developer": False,
            },
        )

        user.is_verified = True
        user.first_name = user.first_name or "App Store"
        user.last_name = user.last_name or "Tester"
        user.gender = "male"

        if grant_pro:
            user.is_pro = True
            user.pro_until = timezone.now() + timedelta(days=30)

        supabase_uid = self._upsert_supabase_user(user, email, password)
        if supabase_uid:
            user.supabase_uid = supabase_uid

        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.height = profile.height or TEST_HEIGHT
        profile.body_weight = profile.body_weight or TEST_WEIGHT
        profile.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} App Store test user: {email}"))
        self.stdout.write(f"  Password: {password}")
        self.stdout.write(f"  PRO: {user.is_pro}")
        if user.pro_until:
            self.stdout.write(f"  PRO until: {user.pro_until.date()}")

        if skip_data:
            self.stdout.write(self.style.WARNING("Skipped sample data (--no-data)."))
            self._remind_sandbox()
            return

        self._add_weight_history(user)
        self._add_body_measurements(user)
        workout_count = self._add_sample_workouts(user)
        program = self._add_workout_program(user)
        self.stdout.write(self.style.SUCCESS(f"  Weight history: 12 entries"))
        self.stdout.write(self.style.SUCCESS(f"  Body measurements: 3 entries"))
        self.stdout.write(self.style.SUCCESS(f"  Workouts: {workout_count}"))
        if program:
            self.stdout.write(self.style.SUCCESS(f"  Program: {program.name} (active, currently on Day 2 - Pull Day)"))
        self._remind_sandbox()

    def _upsert_supabase_user(self, django_user, email, password):
        service_key = settings.SUPABASE_SERVICE_ROLE_KEY
        supabase_url = settings.SUPABASE_URL
        if not service_key or not supabase_url:
            self.stdout.write(self.style.WARNING("SUPABASE_SERVICE_ROLE_KEY not set — skipping Supabase user creation."))
            return None

        headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
        }

        # If we already have the UID, update password + email in Supabase
        if django_user.supabase_uid:
            resp = requests.put(
                f"{supabase_url}/auth/v1/admin/users/{django_user.supabase_uid}",
                headers=headers,
                json={"email": email, "password": password, "email_confirm": True},
            )
            if resp.status_code == 200:
                self.stdout.write(self.style.SUCCESS(f"  Supabase user updated (uid: {django_user.supabase_uid})"))
                return str(django_user.supabase_uid)
            self.stdout.write(self.style.ERROR(f"  Supabase update failed: {resp.text}"))
            return None

        # Create new Supabase user
        resp = requests.post(
            f"{supabase_url}/auth/v1/admin/users",
            headers=headers,
            json={"email": email, "password": password, "email_confirm": True},
        )
        if resp.status_code == 200:
            uid = resp.json()["id"]
            self.stdout.write(self.style.SUCCESS(f"  Supabase user created (uid: {uid})"))
            return uid
        self.stdout.write(self.style.ERROR(f"  Supabase user creation failed: {resp.text}"))
        return None

    def _remind_sandbox(self):
        self.stdout.write(
            self.style.WARNING(
                "Use these credentials in App Store Connect > Sandbox testers and when signing in from the app (Sandbox)."
            )
        )

    def _add_weight_history(self, user):
        WeightHistory.objects.filter(user=user).delete()
        today = timezone.now().date()
        for i in range(12):
            weight_date = today - timedelta(weeks=i)
            weight = TEST_WEIGHT - Decimal(str(i * 0.2))
            dt = timezone.make_aware(timezone.datetime.combine(weight_date, timezone.datetime.min.time()))
            WeightHistory.objects.create(user=user, weight=weight, created_at=dt)

    def _add_body_measurements(self, user):
        BodyMeasurement.objects.filter(user=user).delete()
        today = timezone.now().date()
        for i in range(3):
            measurement_date_only = today - timedelta(weeks=i * 4)
            dt = timezone.make_aware(timezone.datetime.combine(measurement_date_only, timezone.datetime.min.time()))
            BodyMeasurement.objects.create(
                user=user,
                height=TEST_HEIGHT,
                weight=TEST_WEIGHT - Decimal(str(i * 0.8)),
                waist=Decimal("85.0") - Decimal(str(i * 1.5)),
                neck=Decimal("38.0"),
                gender="male",
                created_at=dt,
            )

    def _reset_workout_sequences(self):
        """Ensure workout-related sequences are above max(id) to avoid PK conflicts after imports."""
        with connection.cursor() as cursor:
            for table in ["workout_workout", "workout_workoutexercise", "workout_exerciseset"]:
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE(MAX(id), 0) + 1, false) FROM " + table,
                    [table],
                )

    def _add_sample_workouts(self, user):
        self._reset_workout_sequences()
        exercises = list(Exercise.objects.filter(is_active=True)[:20])
        if not exercises:
            self.stdout.write(self.style.WARNING("No exercises in DB; skipping workouts. Run populate_exercises first."))
            return 0

        templates = [
            {"title": "Push Day", "exercises": ["Bench Press", "Overhead Press", "Tricep", "Lateral Raise"], "intensity": "high"},
            {"title": "Pull Day", "exercises": ["Row", "Pull", "Curl", "Face Pull"], "intensity": "high"},
            {"title": "Leg Day", "exercises": ["Squat", "Deadlift", "Leg Press", "Leg Curl"], "intensity": "high"},
            {"title": "Upper Body", "exercises": ["Bench Press", "Row", "Overhead Press", "Curl"], "intensity": "medium"},
            {"title": "Full Body", "exercises": ["Squat", "Bench Press", "Row", "Overhead Press"], "intensity": "medium"},
        ]

        workout_count = 0
        now = timezone.now()
        for week in range(6):
            for day in range(3):
                days_ago = (week * 7) + (day * 2) + random.randint(0, 1)
                workout_date = now - timedelta(days=days_ago)
                template = random.choice(templates)
                workout = Workout.objects.create(
                    user=user,
                    title=template["title"],
                    datetime=workout_date,
                    duration=random.randint(3600, 7200),
                    intensity=template["intensity"],
                    is_done=True,
                    notes=f"App Store test - {template['title']}",
                )
                exercise_order = 0
                for name_part in template["exercises"]:
                    ex = None
                    for e in exercises:
                        if name_part.lower() in e.name.lower() or e.name.lower() in name_part.lower():
                            ex = e
                            break
                    if not ex:
                        ex = random.choice(exercises)
                    we = WorkoutExercise.objects.create(workout=workout, exercise=ex, order=exercise_order)
                    exercise_order += 1
                    base_weight = Decimal(str(random.randint(40, 100)))
                    for set_num in range(1, random.randint(3, 5) + 1):
                        weight = base_weight + Decimal(str((set_num - 1) * 2.5))
                        ExerciseSet.objects.create(
                            workout_exercise=we,
                            set_number=set_num,
                            reps=random.randint(6, 12),
                            weight=weight,
                            rest_time_before_set=random.randint(60, 120) if set_num > 1 else 0,
                            is_warmup=(set_num == 1 and random.random() < 0.3),
                            reps_in_reserve=random.randint(0, 3),
                        )
                try:
                    workout.calculate_calories()
                    workout.calculate_muscle_recovery()
                    workout.calculate_cns_recovery()
                except Exception:
                    pass
                workout_count += 1
        return workout_count

    def _add_workout_program(self, user):
        WorkoutProgram.objects.filter(user=user).delete()

        exercises = list(Exercise.objects.filter(is_active=True)[:30])
        if not exercises:
            self.stdout.write(self.style.WARNING("No exercises in DB; skipping workout program."))
            return None

        def find_exercise(name_part):
            for e in exercises:
                if name_part.lower() in e.name.lower() or e.name.lower() in name_part.lower():
                    return e
            return random.choice(exercises)

        # 4-day PPL+Rest cycle. activated_at=1 day ago → user is currently on Day 2 (Pull Day).
        program = WorkoutProgram.objects.create(
            user=user,
            name="Push / Pull / Legs",
            cycle_length=4,
            is_active=True,
            activated_at=timezone.now() - timedelta(days=1),
        )

        day_templates = [
            {"day_number": 1, "name": "Push Day",  "is_rest_day": False, "exercises": ["Bench Press", "Overhead Press", "Tricep", "Lateral Raise"]},
            {"day_number": 2, "name": "Pull Day",  "is_rest_day": False, "exercises": ["Row", "Pull", "Curl", "Face Pull"]},
            {"day_number": 3, "name": "Leg Day",   "is_rest_day": False, "exercises": ["Squat", "Deadlift", "Leg Press", "Leg Curl"]},
            {"day_number": 4, "name": "Rest Day",  "is_rest_day": True,  "exercises": []},
        ]

        for day_data in day_templates:
            day = WorkoutProgramDay.objects.create(
                program=program,
                day_number=day_data["day_number"],
                name=day_data["name"],
                is_rest_day=day_data["is_rest_day"],
            )
            for order, name_part in enumerate(day_data["exercises"]):
                WorkoutProgramExercise.objects.create(
                    program_day=day,
                    exercise=find_exercise(name_part),
                    order=order,
                    target_sets=4 if order == 0 else 3,
                )

        return program
