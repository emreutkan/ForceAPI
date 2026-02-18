"""
Workout CRUD operations.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

try:
    from force.throttles import CheckDateRateThrottle
except ImportError:
    from force.throttles import CheckDateRateThrottle
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.utils.http import http_date
from django.db.models import Max
from datetime import datetime, time
from django.core.cache import cache
import logging
from core.mixins import ConditionalGetMixin, CACHE_MAX_AGE_SECONDS
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


class GetWorkoutView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = WorkoutPagination

    def get_last_modified(self, request, workout_id=None, **kwargs):
        if workout_id:
            updated = Workout.objects.filter(
                id=workout_id, user=request.user
            ).values_list("updated_at", flat=True).first()
            return updated
        latest = Workout.objects.filter(
            user=request.user, is_done=True
        ).aggregate(Max("updated_at"))["updated_at__max"]
        return latest

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

            workouts = Workout.objects.filter(
                user=request.user,
                is_done=True
            ).select_related('user').prefetch_related(
                'workoutexercise_set__exercise',
                'workoutexercise_set__sets'
            ).order_by('-created_at')

            latest_modified = workouts.aggregate(Max('updated_at'))['updated_at__max']

            if should_cache:
                cache_key = f'workouts_list_user_{request.user.id}_page_1_size_{page_size}'
                cached = cache.get(cache_key)
                if cached is not None:
                    response = Response(cached['data'])
                    if cached.get('last_modified'):
                        response['Last-Modified'] = cached['last_modified']
                    response['Cache-Control'] = f'private, max-age={CACHE_MAX_AGE_SECONDS}'
                    return response

            paginator = self.pagination_class()
            paginated_workouts = paginator.paginate_queryset(workouts, request)
            serializer = GetWorkoutSerializer(paginated_workouts, many=True)
            paginated_response = paginator.get_paginated_response(serializer.data)

            if should_cache:
                cache_key = f'workouts_list_user_{request.user.id}_page_1_size_{page_size}'
                cache.set(cache_key, {
                    'data': paginated_response.data,
                    'last_modified': http_date(int(latest_modified.timestamp()))
                    if latest_modified else None,
                }, 300)

            return paginated_response


class GetActiveWorkoutView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        w = Workout.objects.filter(user=request.user, is_done=False).values_list("updated_at", flat=True).first()
        return w

    def get(self, request):
        active_workout = Workout.objects.filter(user=request.user, is_done=False).first()
        if active_workout:
            serializer = GetWorkoutSerializer(active_workout, context={'include_insights': True})
            return Response({'active_workout': serializer.data})
        return Response({'active_workout': None}, status=status.HTTP_200_OK)


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


class CheckPreviousWorkoutPerformedView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [CheckDateRateThrottle]

    def get(self, request):
        day = request.query_params.get('day')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        date_str = request.query_params.get('date')

        target_date = None
        if date_str:
            from django.utils.dateparse import parse_date
            target_date = parse_date(date_str)
        if target_date is None and day is not None and month is not None and year is not None:
            try:
                target_date = datetime(int(year), int(month), int(day)).date()
            except (ValueError, TypeError):
                pass

        if target_date is None:
            return Response({
                'error': 'Invalid or missing date. Provide query params: date (YYYY-MM-DD) or day, month, year.'
            }, status=status.HTTP_400_BAD_REQUEST)

        active_workout = Workout.objects.filter(
            user=request.user,
            is_done=False,
            datetime__date=target_date
        ).first()

        if active_workout:
            return Response({
                'workout_performed': False,
                'active_workout': True,
                'date': target_date.isoformat(),
            }, status=status.HTTP_200_OK)

        day_workouts = Workout.objects.filter(
            user=request.user,
            datetime__date=target_date
        ).order_by('-datetime')

        if not day_workouts.exists():
            return Response({
                'workout_performed': False,
                'date': target_date.isoformat(),
                'message': f'No workout performed on {target_date.isoformat()}'
            }, status=status.HTTP_200_OK)

        completed_workout = day_workouts.filter(is_done=True).first()

        if completed_workout:
            if completed_workout.is_rest_day:
                return Response({
                    'workout_performed': True,
                    'is_rest': True,
                    'date': target_date.isoformat(),
                }, status=status.HTTP_200_OK)
            else:
                workout_data = GetWorkoutSerializer(completed_workout).data
                return Response({
                    'workout_performed': True,
                    'is_rest_day': False,
                    'date': target_date.isoformat(),
                    'workout': workout_data,
                    'message': f'Workout performed on {target_date.isoformat()}'
                }, status=status.HTTP_200_OK)

        return Response({
            'workout_performed': False,
            'date': target_date.isoformat(),
            'message': f'No workout performed on {target_date.isoformat()}'
        }, status=status.HTTP_200_OK)


class CheckWorkoutPerformedTodayView(ConditionalGetMixin, APIView):
    """
    GET /api/workout/check-today/?date=YYYY-MM-DD

    Returns a single, consistent shape for "what's the state of today?":
    - status: "none" | "active" | "rest_day" | "completed"
    - date: today (or query date) ISO
    - active_workout: full workout when status is "active", else null (so you don't need /api/workout/active/)
    - completed_workout: full workout or rest-day summary when status is "rest_day" or "completed", else null
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        if date_str:
            from django.utils.dateparse import parse_date
            today = parse_date(date_str) or timezone.now().date()
        else:
            today = timezone.now().date()

        # 1. Any workout in progress (today or not) — treat as "active"
        active_workout = Workout.objects.filter(
            user=request.user,
            is_done=False
        ).select_related('user').prefetch_related(
            'workoutexercise_set__exercise',
            'workoutexercise_set__sets'
        ).first()

        if active_workout:
            serializer = GetWorkoutSerializer(active_workout, context={'include_insights': True})
            return Response({
                'date': today.isoformat(),
                'status': 'active',
                'active_workout': serializer.data,
                'completed_workout': None,
            }, status=status.HTTP_200_OK)

        # 2. What's on today's date?
        today_workouts = Workout.objects.filter(
            user=request.user,
            datetime__date=today
        ).order_by('-datetime')

        if not today_workouts.exists():
            return Response({
                'date': today.isoformat(),
                'status': 'none',
                'active_workout': None,
                'completed_workout': None,
            }, status=status.HTTP_200_OK)

        completed_workout = today_workouts.filter(is_done=True).first()

        if completed_workout:
            if completed_workout.is_rest_day:
                return Response({
                    'date': today.isoformat(),
                    'status': 'rest_day',
                    'active_workout': None,
                    'completed_workout': {
                        'is_rest_day': True,
                        'id': completed_workout.id,
                        'datetime': completed_workout.datetime.isoformat() if completed_workout.datetime else None,
                        'date': today.isoformat(),
                    },
                }, status=status.HTTP_200_OK)
            workout_data = GetWorkoutSerializer(completed_workout).data
            return Response({
                'date': today.isoformat(),
                'status': 'completed',
                'active_workout': None,
                'completed_workout': workout_data,
            }, status=status.HTTP_200_OK)

        # Has entries for today but none completed (edge case)
        return Response({
            'date': today.isoformat(),
            'status': 'none',
            'active_workout': None,
            'completed_workout': None,
        }, status=status.HTTP_200_OK)


class TotalWorkoutsPerformedView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return Workout.objects.filter(user=request.user, is_done=True).aggregate(Max("updated_at"))["updated_at__max"]

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
