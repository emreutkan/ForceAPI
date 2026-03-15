"""
Deterministic coaching endpoints built from workout data only.
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..coaching import (
    build_active_muscle_suggestions,
    build_active_workout_coach,
    build_exercise_optimization_payload,
    build_next_workout_coach,
    build_workout_coach_review,
)
from ..models import Workout, WorkoutExercise


class CoachReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workout_id):
        try:
            workout = Workout.objects.prefetch_related(
                'workoutexercise_set__exercise',
                'workoutexercise_set__sets',
            ).get(id=workout_id, user=request.user)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=404)

        return Response(build_workout_coach_review(request.user, workout))


class NextWorkoutCoachView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_next_workout_coach(request.user))


class ActiveWorkoutCoachView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_active_workout_coach(request.user))


class SuggestNextExerciseView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_workout = (
            Workout.objects.filter(user=request.user, is_done=False)
            .prefetch_related('workoutexercise_set__exercise', 'workoutexercise_set__sets')
            .first()
        )
        suggestions = build_active_muscle_suggestions(request.user, active_workout)
        return Response({
            'suggestions': suggestions,
            'has_active_workout': active_workout is not None,
        }, status=status.HTTP_200_OK)


class ExerciseOptimizationCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workout_exercise_id):
        try:
            workout_exercise = (
                WorkoutExercise.objects
                .select_related('exercise', 'workout')
                .prefetch_related('workout__workoutexercise_set__exercise', 'workout__workoutexercise_set__sets')
                .get(id=workout_exercise_id, workout__user=request.user)
            )
        except WorkoutExercise.DoesNotExist:
            return Response({'error': 'Workout exercise not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = build_exercise_optimization_payload(request.user, workout_exercise)
        exercise = workout_exercise.exercise
        return Response({
            'workout_exercise_id': workout_exercise_id,
            'exercise': {
                'id': exercise.id,
                'name': exercise.name,
                'primary_muscle': exercise.primary_muscle,
                'secondary_muscles': [m for m in (exercise.secondary_muscles or []) if m],
                'category': exercise.category,
            },
            'overall_status': payload['overall_status'],
            'warnings': payload['warnings'],
            'coach': payload['coach'],
        }, status=status.HTTP_200_OK)
