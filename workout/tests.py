from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from exercise.models import Exercise
from .models import (
    ExerciseSet,
    MuscleRecovery,
    Workout,
    WorkoutExercise,
    WorkoutProgram,
    WorkoutProgramDay,
    WorkoutProgramExercise,
    WorkoutMuscleRecovery,
)

User = get_user_model()


class WorkoutTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        self.bench_press = Exercise.objects.create(
            name='Bench Press',
            primary_muscle='chest',
            secondary_muscles=['triceps', 'shoulders'],
            equipment_type='barbell',
            category='compound'
        )
        self.chest_fly = Exercise.objects.create(
            name='Cable Fly',
            primary_muscle='chest',
            secondary_muscles=[],
            equipment_type='cable',
            category='isolation'
        )
        self.barbell_row = Exercise.objects.create(
            name='Barbell Row',
            primary_muscle='lats',
            secondary_muscles=['biceps'],
            equipment_type='barbell',
            category='compound'
        )
        self.squat = Exercise.objects.create(
            name='Squat',
            primary_muscle='quads',
            secondary_muscles=['glutes', 'hamstrings'],
            equipment_type='barbell',
            category='compound'
        )

    def create_completed_exposure(self, exercise, when, one_rm, set_specs=None, title='Logged Workout'):
        workout = Workout.objects.create(
            user=self.user,
            title=title,
            datetime=when,
            duration=3600,
            intensity='medium',
            is_done=True,
            is_rest_day=False,
        )
        workout_exercise = WorkoutExercise.objects.create(
            workout=workout,
            exercise=exercise,
            order=1,
            one_rep_max=one_rm,
        )

        specs = set_specs or [
            {'reps': 8, 'weight': 80, 'rir': 2, 'rest': 120},
        ]
        for index, spec in enumerate(specs, start=1):
            ExerciseSet.objects.create(
                workout_exercise=workout_exercise,
                set_number=index,
                reps=spec['reps'],
                weight=spec['weight'],
                reps_in_reserve=spec.get('rir', 2),
                rest_time_before_set=spec.get('rest', 120),
                is_warmup=False,
            )
        return workout, workout_exercise

    def create_active_workout_with_exercise(self, exercise, set_specs=None):
        workout = Workout.objects.create(
            user=self.user,
            title='Active Workout',
            datetime=timezone.now(),
            intensity='medium',
            is_done=False,
            is_rest_day=False,
        )
        workout_exercise = WorkoutExercise.objects.create(
            workout=workout,
            exercise=exercise,
            order=1,
        )
        for index, spec in enumerate(set_specs or [], start=1):
            ExerciseSet.objects.create(
                workout_exercise=workout_exercise,
                set_number=index,
                reps=spec['reps'],
                weight=spec['weight'],
                reps_in_reserve=spec.get('rir', 2),
                rest_time_before_set=spec.get('rest', 120),
                is_warmup=False,
            )
        return workout, workout_exercise

    def activate_single_day_program(self, exercise, target_sets=3, is_rest_day=False):
        program = WorkoutProgram.objects.create(
            user=self.user,
            name='Test Program',
            cycle_length=1,
            is_active=True,
            activated_at=timezone.now() - timedelta(days=2),
        )
        day = WorkoutProgramDay.objects.create(
            program=program,
            day_number=1,
            name='Chest Day' if not is_rest_day else 'Rest',
            is_rest_day=is_rest_day,
        )
        if not is_rest_day:
            WorkoutProgramExercise.objects.create(
                program_day=day,
                exercise=exercise,
                order=1,
                target_sets=target_sets,
            )
        return program, day

    def create_under_recovery(self, muscle_group, source_workout):
        return MuscleRecovery.objects.create(
            user=self.user,
            muscle_group=muscle_group,
            fatigue_score=12,
            total_sets=5,
            recovery_hours=48,
            recovery_until=timezone.now() + timedelta(hours=24),
            source_workout=source_workout,
            is_recovered=False,
        )

    def test_create_workout(self):
        response = self.client.post('/api/workout/create/', {'title': 'Test Workout'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Workout.objects.count(), 1)

    def test_get_workout(self):
        workout = Workout.objects.create(
            user=self.user,
            title='Test Workout',
            datetime=timezone.now(),
            intensity='medium',
        )
        response = self.client.get(f'/api/workout/list/{workout.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_add_exercise_to_workout(self):
        workout = Workout.objects.create(
            user=self.user,
            title='Test Workout',
            datetime=timezone.now(),
            intensity='medium',
        )
        response = self.client.post(f'/api/workout/{workout.id}/add_exercise/', {'exercise_id': self.bench_press.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkoutExercise.objects.count(), 1)
        self.assertIn('coach', response.data)

    def test_complete_workout(self):
        workout = Workout.objects.create(
            user=self.user,
            title='Test Workout',
            datetime=timezone.now(),
            intensity='medium',
        )
        response = self.client.post(f'/api/workout/{workout.id}/complete/', {'duration': 60})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workout.refresh_from_db()
        self.assertTrue(workout.is_done)

    def test_next_coach_skips_under_recovered_program_day(self):
        source_workout, _ = self.create_completed_exposure(
            self.bench_press,
            timezone.now() - timedelta(days=1),
            100,
        )
        self.create_under_recovery('chest', source_workout)
        self.activate_single_day_program(self.bench_press, target_sets=3)

        response = self.client.get('/api/workout/coach/next/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['session_decision'], 'delay_day')
        self.assertEqual(response.data['exercise_actions'][0]['action'], 'skip')
        self.assertIn('under_recovered', response.data['exercise_actions'][0]['reason_codes'])

    def test_next_coach_pushes_on_progressing_exercise(self):
        now = timezone.now()
        self.create_completed_exposure(self.bench_press, now - timedelta(days=4), 100)
        self.create_completed_exposure(self.bench_press, now - timedelta(days=1), 105)
        self.activate_single_day_program(self.bench_press, target_sets=3)

        response = self.client.get('/api/workout/coach/next/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['exercise_actions'][0]['action'], 'push')
        self.assertEqual(response.data['exercise_actions'][0]['load_delta_pct'], 2.5)

    def test_next_coach_backs_off_on_regressing_exercise(self):
        now = timezone.now()
        self.create_completed_exposure(self.bench_press, now - timedelta(days=4), 100)
        self.create_completed_exposure(self.bench_press, now - timedelta(days=1), 94)
        self.activate_single_day_program(self.bench_press, target_sets=3)

        response = self.client.get('/api/workout/coach/next/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['exercise_actions'][0]['action'], 'backoff')
        self.assertIn('regressing_exercise', response.data['exercise_actions'][0]['reason_codes'])

    def test_next_coach_holds_when_data_is_flat(self):
        now = timezone.now()
        self.create_completed_exposure(self.bench_press, now - timedelta(days=4), 100)
        self.create_completed_exposure(self.bench_press, now - timedelta(days=1), 101)
        self.activate_single_day_program(self.bench_press, target_sets=3)

        response = self.client.get('/api/workout/coach/next/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['exercise_actions'][0]['action'], 'hold')

    def test_next_coach_reports_sparse_data_conservatively(self):
        self.activate_single_day_program(self.bench_press, target_sets=3)

        response = self.client.get('/api/workout/coach/next/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['exercise_actions'][0]['action'], 'hold')
        self.assertIn('insufficient_data', response.data['exercise_actions'][0]['reason_codes'])
        self.assertTrue(any(finding['code'] == 'insufficient_data' for finding in response.data['findings']))

    def test_active_coach_stops_after_excessive_volume(self):
        _workout, workout_exercise = self.create_active_workout_with_exercise(
            self.bench_press,
            set_specs=[
                {'reps': 8, 'weight': 80, 'rir': 2, 'rest': 120},
                {'reps': 8, 'weight': 80, 'rir': 2, 'rest': 120},
                {'reps': 7, 'weight': 80, 'rir': 1, 'rest': 120},
                {'reps': 6, 'weight': 80, 'rir': 1, 'rest': 120},
            ],
        )

        coach_response = self.client.get('/api/workout/active/coach/')
        self.assertEqual(coach_response.status_code, status.HTTP_200_OK)
        self.assertEqual(coach_response.data['live_decision'], 'stop')
        self.assertEqual(coach_response.data['exercise_actions'][0]['action'], 'skip')

        optimization_response = self.client.get(
            f'/api/workout/exercise/{workout_exercise.id}/optimization-check/'
        )
        self.assertEqual(optimization_response.status_code, status.HTTP_200_OK)
        self.assertEqual(optimization_response.data['overall_status'], 'not_recommended')
        self.assertTrue(any(item['type'] == 'too_much_volume' for item in optimization_response.data['warnings']))

    def test_no_program_next_coach_recommends_recovered_muscles(self):
        source_workout, _ = self.create_completed_exposure(
            self.bench_press,
            timezone.now() - timedelta(days=1),
            102,
        )
        self.create_under_recovery('chest', source_workout)
        self.create_completed_exposure(self.barbell_row, timezone.now() - timedelta(days=6), 95)

        response = self.client.get('/api/workout/coach/next/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['program'])
        self.assertTrue(response.data['exercise_actions'])
        self.assertTrue(
            all(action['exercise']['primary_muscle'] != 'chest' for action in response.data['exercise_actions'])
        )

    def test_coach_review_groups_findings(self):
        previous_workout, _ = self.create_completed_exposure(
            self.bench_press,
            timezone.now() - timedelta(days=5),
            100,
        )
        workout, workout_exercise = self.create_completed_exposure(
            self.bench_press,
            timezone.now() - timedelta(hours=1),
            92,
            set_specs=[
                {'reps': 8, 'weight': 75, 'rir': 0, 'rest': 45},
                {'reps': 5, 'weight': 75, 'rir': 0, 'rest': 45},
            ],
            title='Review Workout',
        )
        WorkoutMuscleRecovery.objects.create(
            user=self.user,
            workout=workout,
            muscle_group='chest',
            condition='pre',
            recovery_progress=60,
        )

        response = self.client.get(f'/api/workout/{workout.id}/coach-review/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        finding_codes = {finding['code'] for finding in response.data['findings']}
        self.assertIn('under_recovered', finding_codes)
        self.assertIn('regressing_exercise', finding_codes)
        self.assertTrue(response.data['what_went_wrong'])
        self.assertTrue(response.data['what_to_change_next_time'])
