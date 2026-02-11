"""
Workout CRUD operations.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from datetime import datetime, time
from django.core.cache import cache
import logging
from ..models import Workout, WorkoutExercise
from ..serializers import CreateWorkoutSerializer, GetWorkoutSerializer, UpdateWorkoutSerializer
from ..utils import (
    get_current_recovery_progress,
    create_workout_muscle_recovery,
    recalculate_workout_metrics,
    calculate_workout_exercise_1rm
)

logger = logging.getLogger('workout')


class WorkoutPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CreateWorkoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        active_workout = Workout.objects.filter(user=request.user, is_done=False).first()

        is_rest_day = request.data.get('is_rest_day', False)
        new_workout_is_done = request.data.get('is_done', False)

        workout_datetime_str = request.data.get('workout_date') or request.data.get('date')
        workout_date = None

        if workout_datetime_str:
            try:
                if 'T' in workout_datetime_str:
                    if workout_datetime_str.endswith('Z'):
                        workout_datetime = datetime.fromisoformat(workout_datetime_str.replace('Z', '+00:00'))
                    else:
                        workout_datetime = datetime.fromisoformat(workout_datetime_str)

                    if timezone.is_naive(workout_datetime):
                        workout_datetime = timezone.make_aware(workout_datetime)
                    workout_date = workout_datetime.date()
                else:
                    from django.utils.dateparse import parse_date
                    workout_date = parse_date(workout_datetime_str)
            except (ValueError, TypeError):
                pass
        else:
            workout_date = timezone.now().date()

        if workout_date:
            if is_rest_day:
                existing_workout = Workout.objects.filter(
                    user=request.user,
                    datetime__date=workout_date
                ).first()

                if existing_workout:
                    return Response({
                        'error': 'WORKOUT_EXISTS_FOR_DATE',
                        'message': f'A workout already exists for {workout_date}. Cannot create a rest day for this date.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                existing_rest_day = Workout.objects.filter(
                    user=request.user,
                    datetime__date=workout_date,
                    is_rest_day=True
                ).first()

                if existing_rest_day:
                    return Response({
                        'error': 'REST_DAY_EXISTS_FOR_DATE',
                        'message': f'A rest day already exists for {workout_date}. Cannot create a workout for this date.'
                    }, status=status.HTTP_400_BAD_REQUEST)

        if active_workout and not new_workout_is_done and not is_rest_day:
            return Response({
                'error': 'ACTIVE_WORKOUT_EXISTS',
                'active_workout': active_workout.id,
                'message': 'Cannot create a new active workout. Complete or delete the existing active workout first.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if active_workout and new_workout_is_done and not is_rest_day:
            if workout_date:
                try:
                    workout_datetime = timezone.make_aware(datetime.combine(workout_date, time.min))
                    active_workout_datetime = getattr(active_workout, 'datetime', active_workout.created_at)

                    if workout_datetime and workout_datetime > active_workout_datetime:
                        return Response({
                            'error': 'ACTIVE_WORKOUT_EXISTS',
                            'active_workout': active_workout.id,
                            'message': f'Cannot create workout at {workout_datetime} after active workout at {active_workout_datetime}'
                        }, status=status.HTTP_400_BAD_REQUEST)
                except (ValueError, TypeError) as e:
                    pass

        serializer = CreateWorkoutSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            workout = serializer.save()

            if not workout.is_done and not workout.is_rest_day:
                recovery_progress = get_current_recovery_progress(request.user)
                create_workout_muscle_recovery(request.user, workout, 'pre', recovery_progress)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetWorkoutView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = WorkoutPagination

    def get(self, request, workout_id=None):
        if workout_id:
            try:
                workout = Workout.objects.select_related('user').prefetch_related(
                    'workoutexercise_set__exercise',
                    'workoutexercise_set__sets'
                ).get(id=workout_id, user=request.user)
                serializer = GetWorkoutSerializer(workout, context={'include_insights': True})
                logger.info(f"User {request.user.email} retrieved workout {workout_id}")
                return Response(serializer.data)
            except Workout.DoesNotExist:
                logger.warning(f"User {request.user.email} attempted to access non-existent workout {workout_id}")
                return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.error(f"Error retrieving workout {workout_id} for user {request.user.email}: {str(e)}", exc_info=True)
                return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            page = int(request.query_params.get('page', 1))
            page_size = request.query_params.get('page_size', 20)

            should_cache = page == 1

            if should_cache:
                cache_key = f'workouts_list_user_{request.user.id}_page_1_size_{page_size}'
                cached_response = cache.get(cache_key)
                if cached_response is not None:
                    return Response(cached_response)

            workouts = Workout.objects.filter(
                user=request.user,
                is_done=True
            ).select_related('user').prefetch_related(
                'workoutexercise_set__exercise',
                'workoutexercise_set__sets'
            ).order_by('-created_at')

            paginator = self.pagination_class()
            paginated_workouts = paginator.paginate_queryset(workouts, request)
            serializer = GetWorkoutSerializer(paginated_workouts, many=True)
            paginated_response = paginator.get_paginated_response(serializer.data)

            if should_cache:
                cache.set(cache_key, paginated_response.data, 300)

            return paginated_response


class GetActiveWorkoutView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_workout = Workout.objects.filter(user=request.user, is_done=False).first()
        if active_workout:
            serializer = GetWorkoutSerializer(active_workout, context={'include_insights': True})
            return Response(serializer.data)
        return Response({'error': 'No active workout found'}, status=status.HTTP_404_NOT_FOUND)


class UpdateWorkoutView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, workout_id):
        try:
            workout = Workout.objects.get(id=workout_id, user=request.user)

            if 'date' in request.data and not workout.is_done:
                workout_datetime_str = request.data.get('date')
                if workout_datetime_str:
                    try:
                        if 'T' in workout_datetime_str:
                            if workout_datetime_str.endswith('Z'):
                                new_datetime = datetime.fromisoformat(workout_datetime_str.replace('Z', '+00:00'))
                            else:
                                new_datetime = datetime.fromisoformat(workout_datetime_str)
                            if timezone.is_naive(new_datetime):
                                new_datetime = timezone.make_aware(new_datetime)
                        else:
                            from django.utils.dateparse import parse_date
                            workout_date = parse_date(workout_datetime_str)
                            if workout_date:
                                new_datetime = timezone.make_aware(datetime.combine(workout_date, time.min))
                            else:
                                raise ValueError("Invalid date format")

                        new_date = new_datetime.date()
                        existing_rest_day = Workout.objects.filter(
                            user=request.user,
                            datetime__date=new_date,
                            is_rest_day=True
                        ).exclude(id=workout_id).first()

                        if existing_rest_day:
                            return Response({
                                'error': 'REST_DAY_EXISTS_FOR_DATE',
                                'message': f'A rest day already exists for {new_date}. Cannot update workout to this date.'
                            }, status=status.HTTP_400_BAD_REQUEST)
                    except (ValueError, TypeError):
                        pass

            serializer = UpdateWorkoutSerializer(workout, data=request.data, partial=True)
            if serializer.is_valid():
                updated_workout = serializer.save()
                recalculate_workout_metrics(updated_workout)
                return Response(GetWorkoutSerializer(updated_workout).data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)


class DeleteWorkoutView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, workout_id):
        try:
            workout = Workout.objects.get(id=workout_id, user=request.user)
            workout.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)


class CompleteWorkoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workout_id):
        try:
            workout = Workout.objects.get(id=workout_id, user=request.user)

            if workout.is_done:
                return Response({'error': 'Workout is already completed'}, status=status.HTTP_400_BAD_REQUEST)

            update_fields = ['is_done']

            if 'duration' in request.data:
                try:
                    workout.duration = int(request.data['duration'])
                    update_fields.append('duration')
                except (ValueError, TypeError):
                    return Response({'error': 'Duration must be an integer (seconds)'}, status=status.HTTP_400_BAD_REQUEST)

            if 'intensity' in request.data:
                workout.intensity = request.data['intensity']
                update_fields.append('intensity')
            if 'notes' in request.data:
                workout.notes = request.data['notes']
                update_fields.append('notes')

            workout.is_done = True
            workout.save(update_fields=update_fields)

            workout_exercises = WorkoutExercise.objects.filter(workout=workout)
            for workout_exercise in workout_exercises:
                one_rm = calculate_workout_exercise_1rm(workout_exercise)
                if one_rm is not None:
                    workout_exercise.one_rep_max = one_rm
                    workout_exercise.save()

            recalculate_workout_metrics(workout)

            recovery_progress = get_current_recovery_progress(request.user)
            create_workout_muscle_recovery(request.user, workout, 'post', recovery_progress)

            return Response(GetWorkoutSerializer(workout, context={'include_insights': True}).data, status=status.HTTP_200_OK)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)


# class CheckPreviousWorkoutPerformedView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):

class CheckWorkoutPerformedTodayView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_workout = Workout.objects.filter(
            user=request.user,
            is_done=False
        ).first()

        if active_workout:
            return Response({
                'workout_performed': False,
                'active_workout': True
            }, status=status.HTTP_200_OK)

        today = timezone.now().date()

        today_workouts = Workout.objects.filter(
            user=request.user,
            datetime__date=today
        ).order_by('-datetime')

        if not today_workouts.exists():
            return Response({
                'workout_performed': False,
                'date': today.isoformat(),
                'message': 'No workout performed today'
            }, status=status.HTTP_200_OK)

        completed_workout = today_workouts.filter(is_done=True).first()

        if completed_workout:
            if completed_workout.is_rest_day:
                return Response({
                    'workout_performed': True,
                    'is_rest': True
                }, status=status.HTTP_200_OK)
            else:
                workout_data = GetWorkoutSerializer(completed_workout).data
                return Response({
                    'workout_performed': True,
                    'is_rest_day': False,
                    'date': today.isoformat(),
                    'workout': workout_data,
                    'message': 'Workout performed today'
                }, status=status.HTTP_200_OK)

        return Response({
            'workout_performed': False,
            'date': today.isoformat(),
            'message': 'No workout performed today'
        }, status=status.HTTP_200_OK)


class TotalWorkoutsPerformedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total_workouts = Workout.objects.filter(user=request.user, is_done=True).count()
        first_workout = Workout.objects.filter(user=request.user, is_done=True).order_by('created_at').first()
        if first_workout:
            days_past = (timezone.now() - first_workout.created_at).days
            weeks_past = days_past / 7
        else:
            days_past = 0
            weeks_past = 0

        return Response({
            'total_workouts': total_workouts,
            'days_past': days_past,
            'weeks_past': round(weeks_past, 2)
        })
