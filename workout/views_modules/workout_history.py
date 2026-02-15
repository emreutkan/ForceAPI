"""
Exercise history and calendar views.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Max
from datetime import datetime, timedelta
from calendar import monthrange
from exercise.models import Exercise
from core.mixins import ConditionalGetMixin
from ..models import Workout, WorkoutExercise, ExerciseSet
from ..permissions import is_pro_user
from ..utils import calculate_one_rep_max


class WorkoutPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class GetExercise1RMHistoryView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, exercise_id=None, **kwargs):
        return WorkoutExercise.objects.filter(
            exercise_id=exercise_id,
            workout__user=request.user,
            workout__is_done=True,
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request, exercise_id):
        """
        GET /api/workout/exercise/<exercise_id>/1rm-history/
        Returns 1RM history for a specific exercise across all workouts.
        PRO: Full history
        FREE: Last 30 days only
        """
        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({'error': 'Exercise not found'}, status=status.HTTP_404_NOT_FOUND)
        
        is_pro = is_pro_user(request.user)
        
        workout_exercises = WorkoutExercise.objects.filter(
            exercise_id=exercise_id,
            workout__user=request.user,
            workout__is_done=True,
            one_rep_max__isnull=False
        ).select_related('workout').order_by('-workout__datetime')
        
        if not is_pro:
            thirty_days_ago = timezone.now() - timedelta(days=30)
            workout_exercises = workout_exercises.filter(
                workout__datetime__gte=thirty_days_ago
            )
        
        history = []
        for workout_exercise in workout_exercises:
            history.append({
                'workout_id': workout_exercise.workout.id,
                'workout_title': workout_exercise.workout.title,
                'workout_date': workout_exercise.workout.datetime.isoformat(),
                'one_rep_max': float(workout_exercise.one_rep_max) if workout_exercise.one_rep_max else None
            })
        
        return Response({
            'exercise_id': exercise_id,
            'exercise_name': exercise.name,
            'history': history,
            'total_workouts': len(history),
            'is_pro': is_pro,
            'days_limit': 30 if not is_pro else None
        })


class GetExerciseSetHistoryView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, exercise_id=None, **kwargs):
        return ExerciseSet.objects.filter(
            workout_exercise__exercise_id=exercise_id,
            workout_exercise__workout__user=request.user,
            workout_exercise__workout__is_done=True,
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request, exercise_id):
        """
        GET /api/workout/exercise/<exercise_id>/set-history/
        Returns paginated set history for a specific exercise across all workouts.
        """
        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({'error': 'Exercise not found'}, status=status.HTTP_404_NOT_FOUND)
        
        sets = ExerciseSet.objects.filter(
            workout_exercise__exercise_id=exercise_id,
            workout_exercise__workout__user=request.user,
            workout_exercise__workout__is_done=True
        ).select_related(
            'workout_exercise__workout'
        ).order_by('-workout_exercise__workout__datetime', '-set_number')
        
        paginator = WorkoutPagination()
        paginated_sets = paginator.paginate_queryset(sets, request)
        
        history = []
        for exercise_set in paginated_sets:
            workout = exercise_set.workout_exercise.workout
            history.append({
                'id': exercise_set.id,
                'weight': float(exercise_set.weight),
                'reps': exercise_set.reps,
                'is_warmup': exercise_set.is_warmup,
                'set_number': exercise_set.set_number,
                'workout_id': workout.id,
                'workout_title': workout.title,
                'workout_date': workout.datetime.isoformat(),
            })
        
        return paginator.get_paginated_response(history)


class GetExerciseLastWorkoutView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, exercise_id=None, **kwargs):
        we = WorkoutExercise.objects.filter(
            exercise_id=exercise_id,
            workout__user=request.user,
            workout__is_done=True,
        ).order_by("-workout__datetime").values_list("updated_at", flat=True).first()
        return we

    def get(self, request, exercise_id):
        """
        GET /api/workout/exercise/<exercise_id>/last-workout/
        Returns the last workout where this exercise was performed.
        """
        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response(
                {'error': 'Exercise not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        last_workout_exercise = WorkoutExercise.objects.filter(
            exercise_id=exercise_id,
            workout__user=request.user,
            workout__is_done=True
        ).select_related('workout', 'exercise').order_by('-workout__datetime').first()
        
        if not last_workout_exercise:
            return Response({
                'exercise_id': exercise_id,
                'exercise_name': exercise.name,
                'last_workout': None,
                'message': 'This exercise has not been performed in any completed workout yet.'
            })
        
        workout = last_workout_exercise.workout
        
        sets = ExerciseSet.objects.filter(
            workout_exercise=last_workout_exercise,
            is_warmup=False
        ).order_by('set_number')
        
        sets_data = []
        for s in sets:
            one_rm = None
            if s.weight > 0 and s.reps > 0:
                one_rm = calculate_one_rep_max(s.weight, s.reps)
            sets_data.append({
                'set_number': s.set_number,
                'weight': float(s.weight),
                'reps': s.reps,
                'one_rep_max': float(one_rm) if one_rm else None
            })
        
        return Response({
            'exercise_id': exercise_id,
            'exercise_name': exercise.name,
            'last_workout': {
                'workout_id': workout.id,
                'workout_title': workout.title,
                'workout_date': workout.datetime.isoformat(),
                'one_rep_max': float(last_workout_exercise.one_rep_max) if last_workout_exercise.one_rep_max else None,
                'sets': sets_data,
                'total_sets': len(sets_data),
                'days_ago': (timezone.now().date() - workout.datetime.date()).days
            }
        })


class CalendarView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return Workout.objects.filter(user=request.user).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/workout/calendar/
        Returns calendar data with workouts marked by date.
        Query params: year (required), month (optional), week (optional)
        """
        year = request.query_params.get('year')
        month = request.query_params.get('month', None)
        week = request.query_params.get('week', None)
        
        if not year:
            return Response({
                'error': 'year parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            year = int(year)
            month = int(month) if month else None
            week = int(week) if week else None
        except ValueError:
            return Response({'error': 'Invalid year/month/week format'}, status=status.HTTP_400_BAD_REQUEST)
        
        if week and month and year:
            month_start = datetime(year, month, 1).date()
            days_since_monday = month_start.weekday()
            first_monday = month_start - timedelta(days=days_since_monday)
            week_start = first_monday + timedelta(weeks=week-1)
            week_end = week_start + timedelta(days=6)
            date_range = (week_start, week_end)
        elif month and year:
            start_date = datetime(year, month, 1).date()
            last_day = monthrange(year, month)[1]
            end_date = datetime(year, month, last_day).date()
            date_range = (start_date, end_date)
        elif year:
            start_date = datetime(year, 1, 1).date()
            end_date = datetime(year, 12, 31).date()
            date_range = (start_date, end_date)
        else:
            return Response({'error': 'Invalid parameters'}, status=status.HTTP_400_BAD_REQUEST)
        
        workouts = Workout.objects.filter(
            user=request.user,
            datetime__date__gte=date_range[0],
            datetime__date__lte=date_range[1]
        ).order_by('datetime')
        
        calendar_data = []
        current_date = date_range[0]
        while current_date <= date_range[1]:
            date_str = current_date.isoformat()
            day_workouts = workouts.filter(datetime__date=current_date)
            
            has_workout = day_workouts.filter(is_rest_day=False, is_done=True).exists()
            is_rest_day = day_workouts.filter(is_rest_day=True).exists()
            
            calendar_data.append({
                'date': date_str,
                'day': current_date.day,
                'weekday': current_date.weekday(),
                'has_workout': has_workout,
                'is_rest_day': is_rest_day,
                'workout_count': day_workouts.filter(is_rest_day=False, is_done=True).count(),
                'rest_day_count': day_workouts.filter(is_rest_day=True).count()
            })
            current_date += timedelta(days=1)
        
        return Response({
            'calendar': calendar_data,
            'period': {
                'year': year,
                'month': month,
                'week': week,
                'start_date': date_range[0].isoformat(),
                'end_date': date_range[1].isoformat()
            }
        })


class GetAvailableYearsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return Workout.objects.filter(user=request.user).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/workout/years/
        Returns list of years that have workouts.
        """
        years = Workout.objects.filter(
            user=request.user
        ).values_list('datetime__year', flat=True).distinct().order_by('-datetime__year')
        
        return Response({'years': list(years)})


class CalendarStatsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return Workout.objects.filter(user=request.user).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/workout/calendar/stats/
        Returns stats for a given period.
        Query params: year (required), month (optional), week (optional)
        """
        year = request.query_params.get('year')
        month = request.query_params.get('month', None)
        week = request.query_params.get('week', None)
        
        if not year:
            return Response({'error': 'Year is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            year = int(year)
            month = int(month) if month else None
            week = int(week) if week else None
        except ValueError:
            return Response({'error': 'Invalid year/month/week format'}, status=status.HTTP_400_BAD_REQUEST)
        
        if week and month:
            month_start = datetime(year, month, 1).date()
            days_since_monday = month_start.weekday()
            first_monday = month_start - timedelta(days=days_since_monday)
            week_start = first_monday + timedelta(weeks=week-1)
            week_end = week_start + timedelta(days=6)
            date_range = (week_start, week_end)
            total_days = 7
        elif month:
            start_date = datetime(year, month, 1).date()
            last_day = monthrange(year, month)[1]
            end_date = datetime(year, month, last_day).date()
            date_range = (start_date, end_date)
            total_days = last_day
        else:
            start_date = datetime(year, 1, 1).date()
            end_date = datetime(year, 12, 31).date()
            date_range = (start_date, end_date)
            total_days = 365 if year % 4 != 0 else 366
        
        workouts = Workout.objects.filter(
            user=request.user,
            datetime__date__gte=date_range[0],
            datetime__date__lte=date_range[1]
        )
        
        total_workouts = workouts.filter(is_rest_day=False, is_done=True).count()
        total_rest_days = workouts.filter(is_rest_day=True).count()
        days_with_workouts = workouts.filter(
            is_rest_day=False,
            is_done=True
        ).values_list('datetime__date', flat=True).distinct().count()
        
        days_not_worked = total_days - days_with_workouts - total_rest_days
        
        return Response({
            'total_workouts': total_workouts,
            'total_rest_days': total_rest_days,
            'days_not_worked': max(0, days_not_worked),
            'total_days': total_days,
            'period': {
                'year': year,
                'month': month,
                'week': week,
                'start_date': date_range[0].isoformat(),
                'end_date': date_range[1].isoformat()
            }
        })
