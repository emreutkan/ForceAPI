"""
Personal Records views.
Aggregates best-ever performance per exercise: 1RM, heaviest weight, best volume set.
Data is sourced from existing WorkoutExercise.one_rep_max and ExerciseSet records.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Max
from exercise.models import Exercise
from core.mixins import ConditionalGetMixin
from ..models import WorkoutExercise


class PersonalRecordsListView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return WorkoutExercise.objects.filter(
            workout__user=request.user,
            workout__is_done=True,
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/workout/personal-records/
        Returns all-time PRs grouped by exercise for the authenticated user.
        Includes: best 1RM, heaviest weight lifted, and best single-set volume (weight x reps).
        Only non-warmup sets count toward weight and volume PRs.
        """
        user = request.user

        workout_exercises = WorkoutExercise.objects.filter(
            workout__user=user,
            workout__is_done=True,
        ).select_related('workout', 'exercise').prefetch_related('sets')

        exercise_prs = {}

        for we in workout_exercises:
            exercise = we.exercise
            ex_id = exercise.id
            workout_date = we.workout.datetime

            # Ensure entry exists
            if ex_id not in exercise_prs:
                exercise_prs[ex_id] = {
                    'exercise_id': ex_id,
                    'exercise_name': exercise.name,
                    'primary_muscle': exercise.primary_muscle,
                    'best_1rm': None,
                    'best_1rm_date': None,
                    'best_weight': None,
                    'best_weight_date': None,
                    'best_volume_set': None,
                    'best_volume_set_date': None,
                }

            pr = exercise_prs[ex_id]

            # Best 1RM from WorkoutExercise (Brzycki, already computed on completion)
            if we.one_rep_max is not None:
                orm = float(we.one_rep_max)
                if pr['best_1rm'] is None or orm > pr['best_1rm']:
                    pr['best_1rm'] = orm
                    pr['best_1rm_date'] = workout_date.isoformat()

            # Best weight and best volume set from non-warmup sets
            for s in we.sets.all():
                if s.is_warmup:
                    continue
                weight = float(s.weight)
                reps = s.reps
                volume = weight * reps

                if pr['best_weight'] is None or weight > pr['best_weight']:
                    pr['best_weight'] = weight
                    pr['best_weight_date'] = workout_date.isoformat()

                if volume > 0 and (pr['best_volume_set'] is None or volume > pr['best_volume_set']):
                    pr['best_volume_set'] = round(volume, 2)
                    pr['best_volume_set_date'] = workout_date.isoformat()

        results = sorted(exercise_prs.values(), key=lambda x: x['exercise_name'])
        return Response(results)


class ExercisePersonalRecordView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, exercise_id=None, **kwargs):
        return WorkoutExercise.objects.filter(
            exercise_id=exercise_id,
            workout__user=request.user,
            workout__is_done=True,
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request, exercise_id):
        """
        GET /api/workout/personal-records/<exercise_id>/
        Returns PR detail + chronological 1RM history for a single exercise.
        """
        user = request.user

        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({'error': 'Exercise not found'}, status=status.HTTP_404_NOT_FOUND)

        workout_exercises = WorkoutExercise.objects.filter(
            exercise_id=exercise_id,
            workout__user=user,
            workout__is_done=True,
        ).select_related('workout').prefetch_related('sets').order_by('workout__datetime')

        best_1rm = None
        best_1rm_date = None
        best_weight = None
        best_weight_date = None
        best_volume_set = None
        best_volume_set_date = None
        pr_history = []
        total_workouts = workout_exercises.count()

        for we in workout_exercises:
            workout_date = we.workout.datetime

            if we.one_rep_max is not None:
                orm = float(we.one_rep_max)
                pr_history.append({
                    'workout_id': we.workout.id,
                    'workout_title': we.workout.title,
                    'workout_date': workout_date.isoformat(),
                    'one_rep_max': orm,
                })
                if best_1rm is None or orm > best_1rm:
                    best_1rm = orm
                    best_1rm_date = workout_date.isoformat()

            for s in we.sets.all():
                if s.is_warmup:
                    continue
                weight = float(s.weight)
                reps = s.reps
                volume = weight * reps

                if best_weight is None or weight > best_weight:
                    best_weight = weight
                    best_weight_date = workout_date.isoformat()

                if volume > 0 and (best_volume_set is None or volume > best_volume_set):
                    best_volume_set = round(volume, 2)
                    best_volume_set_date = workout_date.isoformat()

        return Response({
            'exercise_id': exercise_id,
            'exercise_name': exercise.name,
            'primary_muscle': exercise.primary_muscle,
            'best_1rm': best_1rm,
            'best_1rm_date': best_1rm_date,
            'best_weight': best_weight,
            'best_weight_date': best_weight_date,
            'best_volume_set': best_volume_set,
            'best_volume_set_date': best_volume_set_date,
            'pr_history': pr_history,
            'total_workouts': total_workouts,
        })
