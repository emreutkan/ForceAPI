"""
Workout analytics and summary views.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Max
from datetime import datetime, timedelta
from collections import defaultdict
from exercise.models import Exercise
from core.mixins import ConditionalGetMixin
from ..models import Workout, WorkoutExercise, WorkoutMuscleRecovery
from ..permissions import is_pro_user


class VolumeAnalysisView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return Workout.objects.filter(
            user=request.user, is_done=True, is_rest_day=False
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/workout/volume-analysis/
        Analyzes volume per muscle group per week.
        
        Query params:
        - weeks_back (optional): Number of weeks to analyze (default: 12)
        - start_date (optional): Start date in YYYY-MM-DD format
        - end_date (optional): End date in YYYY-MM-DD format
        """
        weeks_back = request.query_params.get('weeks_back', 12)
        start_date_param = request.query_params.get('start_date', None)
        end_date_param = request.query_params.get('end_date', None)
        
        is_pro = is_pro_user(request.user)
        max_weeks_free = 4
        
        try:
            weeks_back = int(weeks_back)
        except ValueError:
            weeks_back = 12
        
        if not is_pro and weeks_back > max_weeks_free:
            weeks_back = max_weeks_free
        
        if start_date_param and end_date_param:
            try:
                start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
                
                if not is_pro:
                    max_days = max_weeks_free * 7
                    days_diff = (end_date - start_date).days
                    if days_diff > max_days:
                        start_date = end_date - timedelta(days=max_days)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_date = timezone.now().date()
            days_since_monday = end_date.weekday()
            current_monday = end_date - timedelta(days=days_since_monday)
            start_date = current_monday - timedelta(weeks=weeks_back)
        
        workouts = Workout.objects.filter(
            user=request.user,
            is_done=True,
            is_rest_day=False,
            datetime__date__gte=start_date,
            datetime__date__lte=end_date
        ).select_related().prefetch_related(
            'workoutexercise_set__exercise',
            'workoutexercise_set__sets'
        ).order_by('datetime')
        
        volume_data = defaultdict(lambda: defaultdict(lambda: {'total_volume': 0.0, 'sets': 0, 'workouts': set()}))
        
        all_muscle_groups = [choice[0] for choice in Exercise.MUSCLE_GROUPS]
        
        for workout in workouts:
            workout_date = workout.datetime.date() if workout.datetime else workout.created_at.date()
            
            days_since_monday = workout_date.weekday()
            week_monday = workout_date - timedelta(days=days_since_monday)
            week_key = week_monday.isoformat()
            
            for workout_exercise in workout.workoutexercise_set.all():
                exercise = workout_exercise.exercise
                sets = workout_exercise.sets.all()
                
                for exercise_set in sets:
                    if exercise_set.is_warmup:
                        continue
                    
                    weight = float(exercise_set.weight) if exercise_set.weight else 0.0
                    reps = exercise_set.reps if exercise_set.reps else 0
                    
                    if weight > 0 and reps > 0:
                        volume = weight * reps
                        
                        primary_muscle = exercise.primary_muscle
                        if primary_muscle:
                            volume_data[week_key][primary_muscle]['total_volume'] += volume
                            volume_data[week_key][primary_muscle]['sets'] += 1
                            volume_data[week_key][primary_muscle]['workouts'].add(workout.id)
                        
                        secondary_muscles = exercise.secondary_muscles or []
                        for secondary_muscle in secondary_muscles:
                            if secondary_muscle:
                                volume_data[week_key][secondary_muscle]['total_volume'] += volume * 0.4
                                volume_data[week_key][secondary_muscle]['sets'] += 1
                                volume_data[week_key][secondary_muscle]['workouts'].add(workout.id)
        
        weeks_list = []
        for week_start_str in sorted(volume_data.keys()):
            week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
            week_end = week_start + timedelta(days=6)
            
            muscle_groups_data = {}
            for muscle_group in all_muscle_groups:
                if muscle_group in volume_data[week_start_str]:
                    data = volume_data[week_start_str][muscle_group]
                    muscle_groups_data[muscle_group] = {
                        'total_volume': round(data['total_volume'], 2),
                        'sets': data['sets'],
                        'workouts': len(data['workouts'])
                    }
                else:
                    muscle_groups_data[muscle_group] = {
                        'total_volume': 0.0,
                        'sets': 0,
                        'workouts': 0
                    }
            
            weeks_list.append({
                'week_start': week_start_str,
                'week_end': week_end.isoformat(),
                'muscle_groups': muscle_groups_data
            })
        
        summary = {}
        for muscle_group in all_muscle_groups:
            volumes = []
            total_sets = 0
            total_workouts = 0
            
            for week_data in weeks_list:
                mg_data = week_data['muscle_groups'][muscle_group]
                if mg_data['total_volume'] > 0:
                    volumes.append(mg_data['total_volume'])
                    total_sets += mg_data['sets']
                    total_workouts += mg_data['workouts']
            
            if volumes:
                summary[muscle_group] = {
                    'average_volume_per_week': round(sum(volumes) / len(volumes), 2),
                    'max_volume_per_week': round(max(volumes), 2),
                    'min_volume_per_week': round(min(volumes), 2),
                    'total_weeks_trained': len(volumes),
                    'total_sets': total_sets,
                    'total_workouts': total_workouts
                }
            else:
                summary[muscle_group] = {
                    'average_volume_per_week': 0.0,
                    'max_volume_per_week': 0.0,
                    'min_volume_per_week': 0.0,
                    'total_weeks_trained': 0,
                    'total_sets': 0,
                    'total_workouts': 0
                }
        
        return Response({
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_weeks': len(weeks_list)
            },
            'weeks': weeks_list,
            'summary': summary,
            'is_pro': is_pro,
            'weeks_limit': max_weeks_free if not is_pro else None
        }, status=status.HTTP_200_OK)


class WorkoutSummaryView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, workout_id=None, **kwargs):
        if workout_id:
            return Workout.objects.filter(id=workout_id, user=request.user).values_list("updated_at", flat=True).first()
        return None

    def get(self, request, workout_id):
        """
        GET /api/workout/<workout_id>/summary/
        Returns workout summary with score, positives, negatives, and neutrals.
        
        Scoring based on:
        1. Recovery: Worked muscles that were recovered (positive) vs still recovering (negative)
        2. 1RM Performance: Higher 1RM (positive), same (neutral), lower (negative)
        """
        try:
            workout = Workout.objects.get(id=workout_id, user=request.user)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)
        
        is_pro = is_pro_user(request.user)
        
        pre_recovery = WorkoutMuscleRecovery.objects.filter(
            workout=workout,
            condition='pre'
        )
        
        pre_recovery_dict = {}
        for record in pre_recovery:
            pre_recovery_dict[record.muscle_group] = float(record.recovery_progress)
        
        workout_exercises = WorkoutExercise.objects.filter(workout=workout).select_related('exercise')
        
        muscles_worked = set()
        exercise_1rm_data = {}
        
        for workout_exercise in workout_exercises:
            exercise = workout_exercise.exercise
            if exercise.primary_muscle:
                muscles_worked.add(exercise.primary_muscle)
            if exercise.secondary_muscles:
                for muscle in exercise.secondary_muscles:
                    if muscle:
                        muscles_worked.add(muscle)
            
            if workout_exercise.one_rep_max:
                exercise_1rm_data[exercise.id] = {
                    'current_1rm': float(workout_exercise.one_rep_max),
                    'exercise_name': exercise.name,
                    'exercise_id': exercise.id
                }
        
        positives = {}
        negatives = {}
        neutrals = {}
        
        for muscle in muscles_worked:
            pre_recovery_progress = pre_recovery_dict.get(muscle, 100.0)
            
            if pre_recovery_progress >= 100.0:
                positives[muscle] = {
                    'type': 'recovery',
                    'message': f'{muscle.capitalize()} was fully recovered before workout',
                    'pre_recovery': pre_recovery_progress
                }
            elif pre_recovery_progress < 70.0:
                negatives[muscle] = {
                    'type': 'recovery',
                    'message': f'{muscle.capitalize()} was only {pre_recovery_progress:.1f}% recovered before workout',
                    'pre_recovery': pre_recovery_progress
                }
            else:
                neutrals[muscle] = {
                    'type': 'recovery',
                    'message': f'{muscle.capitalize()} was {pre_recovery_progress:.1f}% recovered before workout',
                    'pre_recovery': pre_recovery_progress
                }
        
        if is_pro:
            for exercise_id, data in exercise_1rm_data.items():
                current_1rm = data['current_1rm']
                exercise_name = data['exercise_name']
                
                workout_datetime = workout.datetime or workout.created_at
                previous_workout_exercise = WorkoutExercise.objects.filter(
                    exercise_id=exercise_id,
                    workout__user=request.user,
                    workout__is_done=True,
                    one_rep_max__isnull=False
                ).exclude(workout=workout).order_by('-workout__datetime', '-workout__created_at').first()
                
                if previous_workout_exercise and previous_workout_exercise.one_rep_max:
                    previous_1rm = float(previous_workout_exercise.one_rep_max)
                    difference = current_1rm - previous_1rm
                    percent_change = (difference / previous_1rm) * 100 if previous_1rm > 0 else 0
                    
                    if difference > 0:
                        positives[f'{exercise_name}_1rm'] = {
                            'type': '1rm',
                            'message': f'{exercise_name}: 1RM increased from {previous_1rm:.1f}kg to {current_1rm:.1f}kg (+{percent_change:.1f}%)',
                            'current_1rm': current_1rm,
                            'previous_1rm': previous_1rm,
                            'difference': difference,
                            'percent_change': round(percent_change, 1)
                        }
                    elif difference < 0:
                        negatives[f'{exercise_name}_1rm'] = {
                            'type': '1rm',
                            'message': f'{exercise_name}: 1RM decreased from {previous_1rm:.1f}kg to {current_1rm:.1f}kg ({percent_change:.1f}%)',
                            'current_1rm': current_1rm,
                            'previous_1rm': previous_1rm,
                            'difference': difference,
                            'percent_change': round(percent_change, 1)
                        }
                    else:
                        neutrals[f'{exercise_name}_1rm'] = {
                            'type': '1rm',
                            'message': f'{exercise_name}: 1RM maintained at {current_1rm:.1f}kg',
                            'current_1rm': current_1rm,
                            'previous_1rm': previous_1rm,
                            'difference': 0,
                            'percent_change': 0
                        }
                else:
                    neutrals[f'{exercise_name}_1rm'] = {
                        'type': '1rm',
                        'message': f'{exercise_name}: No previous 1RM data to compare',
                        'current_1rm': current_1rm,
                        'previous_1rm': None,
                        'difference': None,
                        'percent_change': None
                    }
        
        base_score = 5.0
        positive_count = len(positives)
        negative_count = len(negatives)
        
        score = base_score + (positive_count * 0.5) - (negative_count * 0.5)
        score = max(0.0, min(10.0, score))
        
        return Response({
            'workout_id': workout.id,
            'score': round(score, 1),
            'positives': positives,
            'negatives': negatives,
            'neutrals': neutrals,
            'summary': {
                'total_positives': positive_count,
                'total_negatives': negative_count,
                'total_neutrals': len(neutrals),
                'muscles_worked': sorted(list(muscles_worked)),
                'exercises_performed': len(exercise_1rm_data)
            },
            'is_pro': is_pro,
            'has_advanced_insights': is_pro
        }, status=status.HTTP_200_OK)
