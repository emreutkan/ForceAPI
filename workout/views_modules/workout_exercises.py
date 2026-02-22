"""
Exercise and set management within workouts.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Max
from exercise.models import Exercise
from ..models import Workout, WorkoutExercise, ExerciseSet
from ..serializers import WorkoutExerciseSerializer, ExerciseSetSerializer
from ..utils import recalculate_workout_metrics


class AddExerciseToWorkoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workout_id):
        exercise_id = request.data.get('exercise_id')
        if not exercise_id:
            return Response({'error': 'exercise_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({'error': 'Exercise not found'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            try:
                workout = Workout.objects.select_for_update().get(id=workout_id, user=request.user)
            except Workout.DoesNotExist:
                return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)

            max_order = workout.workoutexercise_set.aggregate(m=Max('order'))['m'] or 0
            data = {
                'workout': workout.id,
                'exercise': exercise.id,
                'order': max_order + 1
            }
            serializer = WorkoutExerciseSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AddExerciseSetToWorkoutExerciseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workout_exercise_id):
        with transaction.atomic():
            try:
                workout_exercise = WorkoutExercise.objects.select_for_update().get(
                    id=workout_exercise_id, workout__user=request.user
                )
            except WorkoutExercise.DoesNotExist:
                return Response({'error': 'Workout exercise not found'}, status=status.HTTP_404_NOT_FOUND)

            # Use Max instead of count so deleted sets don't cause duplicate set_numbers
            max_set = workout_exercise.sets.aggregate(m=Max('set_number'))['m'] or 0
            set_number = max_set + 1

            data = request.data.copy()
            data['workout_exercise'] = workout_exercise.id
            data['set_number'] = set_number

            # Enforce maximums
            if 'rest_time_before_set' in data and data['rest_time_before_set'] is not None:
                try:
                    rest_time = int(data['rest_time_before_set'])
                    data['rest_time_before_set'] = min(rest_time, 900)
                except (ValueError, TypeError):
                    pass

            if 'total_tut' in data and data['total_tut'] is not None:
                try:
                    tut = int(data['total_tut'])
                    data['total_tut'] = min(tut, 180)
                except (ValueError, TypeError):
                    pass

            serializer = ExerciseSetSerializer(data=data)
            if serializer.is_valid():
                serializer.save()

                workout = workout_exercise.workout
                if workout.rest_timer_paused_at:
                    workout.rest_timer_paused_at = None
                    workout.save(update_fields=['rest_timer_paused_at'])
                recalculate_workout_metrics(workout)

                return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateExerciseSetView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, set_id):
        try:
            exercise_set = ExerciseSet.objects.get(id=set_id, workout_exercise__workout__user=request.user)

            data = request.data.copy()
            # Enforce maximums
            if 'rest_time_before_set' in data and data['rest_time_before_set'] is not None:
                try:
                    rest_time = int(data['rest_time_before_set'])
                    data['rest_time_before_set'] = min(rest_time, 900)
                except (ValueError, TypeError):
                    pass

            if 'total_tut' in data and data['total_tut'] is not None:
                try:
                    tut = int(data['total_tut'])
                    data['total_tut'] = min(tut, 180)
                except (ValueError, TypeError):
                    pass

            serializer = ExerciseSetSerializer(exercise_set, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()

                workout = exercise_set.workout_exercise.workout
                recalculate_workout_metrics(workout)

                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except ExerciseSet.DoesNotExist:
            return Response({'error': 'Set not found'}, status=status.HTTP_404_NOT_FOUND)


class DeleteExerciseSetView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, set_id):
        try:
            exercise_set = ExerciseSet.objects.get(id=set_id, workout_exercise__workout__user=request.user)
            workout = exercise_set.workout_exercise.workout
            exercise_set.delete()

            recalculate_workout_metrics(workout)

            return Response(status=status.HTTP_204_NO_CONTENT)
        except ExerciseSet.DoesNotExist:
            return Response({'error': 'Set not found'}, status=status.HTTP_404_NOT_FOUND)


class DeleteWorkoutExerciseView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, workout_exercise_id):
        try:
            workout_exercise = WorkoutExercise.objects.get(id=workout_exercise_id, workout__user=request.user)
            workout_exercise_order = workout_exercise.order
            current_workout = workout_exercise.workout
            workout_exercise.delete()

            for exercise in WorkoutExercise.objects.filter(workout=current_workout, order__gt=workout_exercise_order):
                exercise.order = exercise.order - 1
                exercise.save()

            recalculate_workout_metrics(current_workout)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except WorkoutExercise.DoesNotExist:
            return Response({'error': 'Exercise not found in workout'}, status=status.HTTP_404_NOT_FOUND)


class UpdateExerciseOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workout_id):
        try:
            workout = Workout.objects.get(id=workout_id, user=request.user)

            exercise_orders = request.data.get('exercise_orders', [])

            for item in exercise_orders:
                try:
                    workout_exercise = WorkoutExercise.objects.get(id=item['id'], workout=workout)
                    workout_exercise.order = item['order']
                    workout_exercise.save()
                except WorkoutExercise.DoesNotExist:
                    continue

            return Response(status=status.HTTP_200_OK)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)
