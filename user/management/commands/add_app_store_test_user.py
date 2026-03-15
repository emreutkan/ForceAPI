"""
Creates or updates an App Store test user for TestFlight / App Review.
Fills the account with test data: profile, weight history, body measurements,
background workouts, and featured coaching scenarios.
"""
import random
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from body_measurements.models import BodyMeasurement
from exercise.models import Exercise
from user.models import CustomUser, UserProfile, WeightHistory
from workout.models import (
    ExerciseSet,
    Workout,
    WorkoutExercise,
    WorkoutProgram,
    WorkoutProgramDay,
    WorkoutProgramExercise,
)
from workout.utils import calculate_workout_exercise_1rm, create_workout_muscle_recovery


APP_STORE_TEST_EMAIL = "appstore.test@force.test"
APP_STORE_TEST_PASSWORD = "TestUser123!"

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

        self._reset_training_data(user)
        self._add_weight_history(user)
        self._add_body_measurements(user)
        background_workout_count = self._add_background_workouts(user)
        showcase = self._add_coaching_showcase(user)
        program = self._add_workout_program(
            user,
            activated_at=showcase["program_activation_at"],
            pull_day_exercises=showcase["pull_day_exercises"],
        )

        self.stdout.write(self.style.SUCCESS("  Weight history: 12 entries"))
        self.stdout.write(self.style.SUCCESS("  Body measurements: 3 entries"))
        self.stdout.write(
            self.style.SUCCESS(f"  Workouts: {background_workout_count + showcase['workout_count']}")
        )
        if program:
            self.stdout.write(self.style.SUCCESS(f"  Program: {program.name} (active, currently on Day 2 - Pull Day)"))
        self.stdout.write(self.style.SUCCESS(f"  Coach review workout: {showcase['coach_review_title']}"))
        self.stdout.write(self.style.SUCCESS(f"  Active workout: {showcase['active_workout_title']}"))
        self._remind_sandbox()

    def _upsert_supabase_user(self, django_user, email, password):
        service_key = settings.SUPABASE_SERVICE_ROLE_KEY
        supabase_url = settings.SUPABASE_URL
        if not service_key or not supabase_url:
            self.stdout.write(self.style.WARNING("SUPABASE_SERVICE_ROLE_KEY not set - skipping Supabase user creation."))
            return None

        headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
        }

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

    def _reset_training_data(self, user):
        WorkoutProgram.objects.filter(user=user).delete()
        Workout.objects.filter(user=user).delete()

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
        with connection.cursor() as cursor:
            for table in ["workout_workout", "workout_workoutexercise", "workout_exerciseset"]:
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE(MAX(id), 0) + 1, false) FROM " + table,
                    [table],
                )

    def _find_exercise(self, exercises, aliases, primary_muscle=None, category=None, equipment_types=None):
        aliases = [alias.lower() for alias in aliases if alias]
        equipment_types = set(equipment_types or [])

        def matches_filters(exercise):
            if primary_muscle and exercise.primary_muscle != primary_muscle:
                return False
            if category and exercise.category != category:
                return False
            if equipment_types and exercise.equipment_type not in equipment_types:
                return False
            return True

        filtered = [exercise for exercise in exercises if matches_filters(exercise)]
        for alias in aliases:
            for exercise in filtered:
                name = exercise.name.lower()
                if alias in name or name in alias:
                    return exercise

        if filtered:
            return filtered[0]
        return exercises[0] if exercises else None

    def _create_seed_workout(
        self,
        user,
        title,
        when,
        intensity,
        exercise_specs,
        *,
        duration=4200,
        is_done=True,
        notes=None,
        pre_recovery=None,
    ):
        workout = Workout.objects.create(
            user=user,
            title=title,
            datetime=when,
            duration=duration,
            intensity=intensity,
            is_done=is_done,
            is_rest_day=False,
            notes=notes or f"App Store test - {title}",
        )

        if pre_recovery:
            create_workout_muscle_recovery(user, workout, "pre", pre_recovery)

        workout_exercises = []
        for order, spec in enumerate(exercise_specs):
            workout_exercise = WorkoutExercise.objects.create(
                workout=workout,
                exercise=spec["exercise"],
                order=order,
            )

            for set_number, set_spec in enumerate(spec["sets"], start=1):
                ExerciseSet.objects.create(
                    workout_exercise=workout_exercise,
                    set_number=set_number,
                    reps=set_spec["reps"],
                    weight=Decimal(str(set_spec["weight"])),
                    rest_time_before_set=set_spec.get("rest", 120),
                    is_warmup=set_spec.get("is_warmup", False),
                    reps_in_reserve=set_spec.get("rir", 2),
                    eccentric_time=set_spec.get("eccentric_time"),
                    concentric_time=set_spec.get("concentric_time"),
                    total_tut=set_spec.get("total_tut"),
                )

            one_rep_max = calculate_workout_exercise_1rm(workout_exercise)
            if one_rep_max is not None:
                workout_exercise.one_rep_max = Decimal(str(one_rep_max))
                workout_exercise.save(update_fields=["one_rep_max"])
            workout_exercises.append(workout_exercise)

        if is_done:
            try:
                workout.calculate_calories()
                workout.calculate_muscle_recovery()
                workout.calculate_cns_recovery()
            except Exception:
                pass

        return workout, workout_exercises

    def _add_background_workouts(self, user):
        self._reset_workout_sequences()
        exercises = list(Exercise.objects.filter(is_active=True)[:20])
        if not exercises:
            self.stdout.write(self.style.WARNING("No exercises in DB; skipping workouts. Run populate_exercises first."))
            return 0

        rng = random.Random(f"app-store-test-user:{user.email}")
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
                days_ago = 21 + (week * 7) + (day * 2) + rng.randint(0, 1)
                workout_date = now - timedelta(days=days_ago)
                template = rng.choice(templates)
                workout = Workout.objects.create(
                    user=user,
                    title=template["title"],
                    datetime=workout_date,
                    duration=rng.randint(3600, 7200),
                    intensity=template["intensity"],
                    is_done=True,
                    notes=f"App Store test - {template['title']}",
                )

                for order, name_part in enumerate(template["exercises"]):
                    exercise = None
                    for candidate in exercises:
                        candidate_name = candidate.name.lower()
                        if name_part.lower() in candidate_name or candidate_name in name_part.lower():
                            exercise = candidate
                            break
                    if not exercise:
                        exercise = rng.choice(exercises)

                    workout_exercise = WorkoutExercise.objects.create(
                        workout=workout,
                        exercise=exercise,
                        order=order,
                    )
                    base_weight = Decimal(str(rng.randint(40, 100)))
                    for set_num in range(1, rng.randint(3, 5) + 1):
                        weight = base_weight + Decimal(str((set_num - 1) * 2.5))
                        ExerciseSet.objects.create(
                            workout_exercise=workout_exercise,
                            set_number=set_num,
                            reps=rng.randint(6, 12),
                            weight=weight,
                            rest_time_before_set=rng.randint(60, 120) if set_num > 1 else 0,
                            is_warmup=(set_num == 1 and rng.random() < 0.3),
                            reps_in_reserve=rng.randint(0, 3),
                        )

                    one_rep_max = calculate_workout_exercise_1rm(workout_exercise)
                    if one_rep_max is not None:
                        workout_exercise.one_rep_max = Decimal(str(one_rep_max))
                        workout_exercise.save(update_fields=["one_rep_max"])

                try:
                    workout.calculate_calories()
                    workout.calculate_muscle_recovery()
                    workout.calculate_cns_recovery()
                except Exception:
                    pass
                workout_count += 1

        return workout_count

    def _add_coaching_showcase(self, user):
        exercises = list(Exercise.objects.filter(is_active=True))
        if not exercises:
            self.stdout.write(self.style.WARNING("No exercises in DB; skipping coaching showcase."))
            return {
                "workout_count": 0,
                "program_activation_at": timezone.now(),
                "pull_day_exercises": [],
                "coach_review_title": "N/A",
                "active_workout_title": "N/A",
            }

        bench_press = self._find_exercise(
            exercises,
            ["bench press", "barbell bench press", "chest press"],
            primary_muscle="chest",
            category="compound",
        )
        cable_fly = self._find_exercise(
            exercises,
            ["cable fly", "pec deck", "machine fly", "chest fly"],
            primary_muscle="chest",
            category="isolation",
        )
        barbell_row = self._find_exercise(
            exercises,
            ["barbell row", "bent over row", "seated row", "row"],
            primary_muscle="lats",
            category="compound",
        )
        shrug = self._find_exercise(
            exercises,
            ["barbell shrug", "dumbbell shrug", "shrug"],
            primary_muscle="traps",
        )
        biceps_curl = self._find_exercise(
            exercises,
            ["ez bar curl", "preacher curl", "dumbbell curl", "cable curl", "curl"],
            primary_muscle="biceps",
            category="isolation",
        )

        now = timezone.now()

        self._create_seed_workout(
            user,
            "Bench Benchmark",
            now - timedelta(days=15),
            "high",
            [
                {
                    "exercise": bench_press,
                    "sets": [
                        {"reps": 8, "weight": 80, "rir": 2, "rest": 150},
                        {"reps": 8, "weight": 80, "rir": 2, "rest": 150},
                        {"reps": 7, "weight": 82.5, "rir": 1, "rest": 180},
                    ],
                },
                {
                    "exercise": cable_fly,
                    "sets": [
                        {"reps": 12, "weight": 25, "rir": 2, "rest": 60},
                        {"reps": 12, "weight": 25, "rir": 2, "rest": 60},
                        {"reps": 11, "weight": 27.5, "rir": 1, "rest": 60},
                    ],
                },
            ],
            notes="Baseline pressing workout for review comparisons.",
        )

        self._create_seed_workout(
            user,
            "Pull Benchmark",
            now - timedelta(days=13),
            "high",
            [
                {
                    "exercise": barbell_row,
                    "sets": [
                        {"reps": 8, "weight": 70, "rir": 2, "rest": 120},
                        {"reps": 8, "weight": 70, "rir": 2, "rest": 120},
                        {"reps": 7, "weight": 72.5, "rir": 1, "rest": 150},
                    ],
                },
                {
                    "exercise": shrug,
                    "sets": [
                        {"reps": 12, "weight": 30, "rir": 2, "rest": 75},
                        {"reps": 12, "weight": 30, "rir": 2, "rest": 75},
                        {"reps": 10, "weight": 32.5, "rir": 1, "rest": 90},
                    ],
                },
                {
                    "exercise": biceps_curl,
                    "sets": [
                        {"reps": 10, "weight": 30, "rir": 2, "rest": 60},
                        {"reps": 10, "weight": 30, "rir": 2, "rest": 60},
                        {"reps": 9, "weight": 32.5, "rir": 1, "rest": 60},
                    ],
                },
            ],
            notes="Stable pull benchmark for coaching comparisons.",
        )

        self._create_seed_workout(
            user,
            "Bench Progress Check",
            now - timedelta(days=7),
            "high",
            [
                {
                    "exercise": bench_press,
                    "sets": [
                        {"reps": 8, "weight": 82.5, "rir": 2, "rest": 150},
                        {"reps": 8, "weight": 82.5, "rir": 2, "rest": 150},
                        {"reps": 7, "weight": 85, "rir": 1, "rest": 180},
                    ],
                },
            ],
            notes="Improved pressing exposure before the coach review workout.",
        )

        self._create_seed_workout(
            user,
            "Pull Progress Check",
            now - timedelta(days=3),
            "high",
            [
                {
                    "exercise": barbell_row,
                    "sets": [
                        {"reps": 8, "weight": 75, "rir": 2, "rest": 120},
                        {"reps": 8, "weight": 75, "rir": 2, "rest": 120},
                        {"reps": 6, "weight": 77.5, "rir": 1, "rest": 150},
                    ],
                },
                {
                    "exercise": shrug,
                    "sets": [
                        {"reps": 12, "weight": 35, "rir": 2, "rest": 75},
                        {"reps": 12, "weight": 35, "rir": 2, "rest": 75},
                        {"reps": 10, "weight": 37.5, "rir": 1, "rest": 90},
                    ],
                },
            ],
            notes="Recent pull exposure that should trigger progression on traps.",
        )

        self._create_seed_workout(
            user,
            "Curl Slump",
            now - timedelta(days=2),
            "medium",
            [
                {
                    "exercise": biceps_curl,
                    "sets": [
                        {"reps": 10, "weight": 27.5, "rir": 2, "rest": 60},
                        {"reps": 9, "weight": 27.5, "rir": 1, "rest": 60},
                        {"reps": 8, "weight": 30, "rir": 1, "rest": 75},
                    ],
                },
            ],
            notes="Recent curl regression for next-workout coaching.",
        )

        self._create_seed_workout(
            user,
            "Arm Focus Pump",
            now - timedelta(hours=20),
            "high",
            [
                {
                    "exercise": biceps_curl,
                    "sets": [
                        {"reps": 12, "weight": 25, "rir": 0, "rest": 45},
                        {"reps": 11, "weight": 25, "rir": 0, "rest": 45},
                        {"reps": 10, "weight": 25, "rir": 0, "rest": 45},
                        {"reps": 9, "weight": 25, "rir": 0, "rest": 45},
                        {"reps": 8, "weight": 25, "rir": 0, "rest": 45},
                    ],
                },
            ],
            notes="Deliberately leaves biceps under-recovered for today's pull recommendations.",
        )

        coach_review_workout, _ = self._create_seed_workout(
            user,
            "Coach Review - Press Day",
            now - timedelta(hours=5),
            "high",
            [
                {
                    "exercise": bench_press,
                    "sets": [
                        {"reps": 8, "weight": 75, "rir": 0, "rest": 45},
                        {"reps": 6, "weight": 75, "rir": 0, "rest": 45},
                        {"reps": 5, "weight": 75, "rir": 0, "rest": 45},
                    ],
                },
                {
                    "exercise": cable_fly,
                    "sets": [
                        {"reps": 12, "weight": 22.5, "rir": 1, "rest": 45},
                        {"reps": 10, "weight": 22.5, "rir": 0, "rest": 45},
                    ],
                },
            ],
            notes="Designed to produce a strong coach-review payload.",
            pre_recovery={
                "chest": 62,
                "triceps": 74,
                "shoulders": 82,
            },
        )

        active_workout, _ = self._create_seed_workout(
            user,
            "Pull Day Live Session",
            now - timedelta(minutes=15),
            "medium",
            [
                {
                    "exercise": barbell_row,
                    "sets": [
                        {"reps": 8, "weight": 75, "rir": 2, "rest": 120},
                        {"reps": 8, "weight": 75, "rir": 2, "rest": 120},
                        {"reps": 7, "weight": 75, "rir": 1, "rest": 120},
                        {"reps": 6, "weight": 75, "rir": 1, "rest": 120},
                    ],
                },
            ],
            is_done=False,
            duration=0,
            notes="Live workout for active coach and optimization-check testing.",
        )

        return {
            "workout_count": 8,
            "program_activation_at": now - timedelta(hours=8),
            "pull_day_exercises": [
                {"exercise": barbell_row, "target_sets": 4},
                {"exercise": shrug, "target_sets": 3},
                {"exercise": biceps_curl, "target_sets": 3},
            ],
            "coach_review_title": f"{coach_review_workout.title} (id={coach_review_workout.id})",
            "active_workout_title": f"{active_workout.title} (id={active_workout.id})",
        }

    def _add_workout_program(self, user, activated_at=None, pull_day_exercises=None):
        WorkoutProgram.objects.filter(user=user).delete()

        exercises = list(Exercise.objects.filter(is_active=True)[:30])
        if not exercises:
            self.stdout.write(self.style.WARNING("No exercises in DB; skipping workout program."))
            return None

        def find_exercise(name_part):
            for exercise in exercises:
                exercise_name = exercise.name.lower()
                if name_part.lower() in exercise_name or exercise_name in name_part.lower():
                    return exercise
            return random.choice(exercises)

        program = WorkoutProgram.objects.create(
            user=user,
            name="Push / Pull / Legs",
            cycle_length=4,
            is_active=True,
            activated_at=activated_at or (timezone.now() - timedelta(days=1)),
        )

        day_templates = [
            {"day_number": 1, "name": "Push Day", "is_rest_day": False, "exercises": ["Bench Press", "Overhead Press", "Tricep", "Lateral Raise"]},
            {"day_number": 2, "name": "Pull Day", "is_rest_day": False, "exercises": pull_day_exercises or ["Row", "Pull", "Curl", "Face Pull"]},
            {"day_number": 3, "name": "Leg Day", "is_rest_day": False, "exercises": ["Squat", "Deadlift", "Leg Press", "Leg Curl"]},
            {"day_number": 4, "name": "Rest Day", "is_rest_day": True, "exercises": []},
        ]

        for day_data in day_templates:
            day = WorkoutProgramDay.objects.create(
                program=program,
                day_number=day_data["day_number"],
                name=day_data["name"],
                is_rest_day=day_data["is_rest_day"],
            )
            for order, exercise_config in enumerate(day_data["exercises"]):
                if isinstance(exercise_config, dict):
                    exercise = exercise_config["exercise"]
                    target_sets = exercise_config.get("target_sets", 3)
                else:
                    exercise = find_exercise(exercise_config)
                    target_sets = 4 if order == 0 else 3
                WorkoutProgramExercise.objects.create(
                    program_day=day,
                    exercise=exercise,
                    order=order,
                    target_sets=target_sets,
                )

        return program
