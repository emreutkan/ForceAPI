"""
Recovery and recommendations views.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import models
from django.db.models import Max
from core.mixins import ConditionalGetMixin
from ..models import Workout, WorkoutExercise, TrainingResearch, MuscleRecovery, CNSRecovery
from ..serializers import TrainingResearchSerializer, MuscleRecoverySerializer, CNSRecoverySerializer
from ..permissions import is_pro_user, get_pro_response


class GetRecoveryRecommendationsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return Workout.objects.filter(
            user=request.user, is_done=True, is_rest_day=False
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/workout/recommendations/recovery/
        Returns recovery recommendations based on user's last workout.
        PRO only feature.
        """
        if not is_pro_user(request.user):
            return get_pro_response()
        
        last_workout = Workout.objects.filter(
            user=request.user,
            is_done=True,
            is_rest_day=False
        ).order_by('-datetime').first()
        
        if not last_workout:
            return Response({
                'message': 'No completed workouts found',
                'recommendations': []
            })
        
        workout_exercises = WorkoutExercise.objects.filter(workout=last_workout).select_related('exercise')
        muscle_groups = set()
        exercise_types = set()
        
        for we in workout_exercises:
            if we.exercise.primary_muscle:
                muscle_groups.add(we.exercise.primary_muscle)
            if we.exercise.category:
                exercise_types.add(we.exercise.category)
        
        research_items = TrainingResearch.objects.filter(
            is_active=True,
            category__in=['MUSCLE_RECOVERY', 'MUSCLE_GROUPS', 'PROTEIN_SYNTHESIS']
        )
        
        recommendations = []
        for research in research_items:
            applicable = False
            if 'all' in research.applicable_muscle_groups:
                applicable = True
            elif any(mg in research.applicable_muscle_groups for mg in muscle_groups):
                applicable = True
            
            if applicable:
                params = research.parameters or {}
                recommendations.append({
                    'title': research.title,
                    'summary': research.summary,
                    'category': research.category,
                    'confidence_score': float(research.confidence_score),
                    'parameters': params,
                    'source_url': research.source_url
                })
        
        hours_since_workout = (timezone.now() - last_workout.datetime).total_seconds() / 3600
        
        recovery_hours = 48
        for rec in recommendations:
            if 'recovery_time_hours' in rec.get('parameters', {}):
                recovery_hours = rec['parameters']['recovery_time_hours']
                break
        
        return Response({
            'last_workout_id': last_workout.id,
            'last_workout_date': last_workout.datetime.isoformat(),
            'hours_since_workout': round(hours_since_workout, 1),
            'muscle_groups_worked': sorted(list(muscle_groups)),
            'recommended_recovery_hours': recovery_hours,
            'is_recovered': hours_since_workout >= recovery_hours,
            'recommendations': sorted(recommendations, key=lambda x: x['confidence_score'], reverse=True)
        })


class GetRestPeriodRecommendationsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, workout_exercise_id=None, **kwargs):
        w = WorkoutExercise.objects.filter(
            id=workout_exercise_id, workout__user=request.user
        ).values_list("updated_at", flat=True).first()
        return w

    def get(self, request, workout_exercise_id):
        """
        GET /api/workout/exercise/<workout_exercise_id>/rest-recommendations/
        Returns recommended rest periods for an exercise based on research.
        PRO only feature.
        """
        if not is_pro_user(request.user):
            return get_pro_response()
        try:
            workout_exercise = WorkoutExercise.objects.get(
                id=workout_exercise_id,
                workout__user=request.user
            )
        except WorkoutExercise.DoesNotExist:
            return Response({'error': 'Workout exercise not found'}, status=status.HTTP_404_NOT_FOUND)
        
        exercise = workout_exercise.exercise
        is_compound = exercise.category == 'compound'
        
        research = TrainingResearch.objects.filter(
            is_active=True,
            category='REST_PERIODS',
            is_validated=True
        ).first()
        
        if research and research.parameters:
            params = research.parameters
            if is_compound:
                min_rest = params.get('compound_rest_min_seconds', 120)
                max_rest = params.get('compound_rest_max_seconds', 300)
            else:
                min_rest = params.get('isolation_rest_min_seconds', 60)
                max_rest = params.get('isolation_rest_max_seconds', 180)
        else:
            if is_compound:
                min_rest = 120
                max_rest = 300
            else:
                min_rest = 60
                max_rest = 180
        
        return Response({
            'exercise_id': exercise.id,
            'exercise_name': exercise.name,
            'exercise_type': exercise.category,
            'recommended_rest_seconds': {
                'min': min_rest,
                'max': max_rest,
                'optimal': (min_rest + max_rest) // 2
            },
            'research_source': research.source_url if research else None
        })


class GetTrainingFrequencyRecommendationsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/workout/recommendations/frequency/
        Returns training frequency recommendations based on research.
        PRO only feature.
        """
        if not is_pro_user(request.user):
            return get_pro_response()
        
        research = TrainingResearch.objects.filter(
            is_active=True,
            category='TRAINING_FREQUENCY',
            is_validated=True
        ).order_by('-priority', '-confidence_score').first()
        
        if research and research.parameters:
            params = research.parameters
            recommendations = {
                'optimal_frequency_per_week': {
                    'min': params.get('optimal_frequency_min', 2),
                    'max': params.get('optimal_frequency_max', 3)
                },
                'max_days_between_sessions': params.get('max_days_between_sessions', 4),
                'protein_synthesis_window_hours': params.get('protein_synthesis_window_hours', 48),
                'research_title': research.title,
                'research_summary': research.summary,
                'source_url': research.source_url
            }
        else:
            recommendations = {
                'optimal_frequency_per_week': {'min': 2, 'max': 3},
                'max_days_between_sessions': 4,
                'protein_synthesis_window_hours': 48,
                'research_title': None,
                'research_summary': None,
                'source_url': None
            }
        
        return Response(recommendations)


class GetRelevantResearchView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/workout/research/
        Returns relevant research articles based on query params.
        Query params: category, muscle_group, exercise_type, tags
        PRO only feature.
        """
        if not is_pro_user(request.user):
            return get_pro_response()
        
        category = request.query_params.get('category', None)
        muscle_group = request.query_params.get('muscle_group', None)
        exercise_type = request.query_params.get('exercise_type', None)
        tags = request.query_params.getlist('tags', [])
        
        research = TrainingResearch.objects.filter(is_active=True)
        
        if category:
            research = research.filter(category=category)
        
        if muscle_group:
            research = research.filter(
                models.Q(applicable_muscle_groups__contains=[muscle_group]) |
                models.Q(applicable_muscle_groups__contains=['all'])
            )
        
        if exercise_type:
            research = research.filter(
                models.Q(applicable_exercise_types__contains=[exercise_type]) |
                models.Q(applicable_exercise_types__contains=['all'])
            )
        
        if tags:
            for tag in tags:
                research = research.filter(tags__contains=[tag])
        
        serializer = TrainingResearchSerializer(research.order_by('-priority', '-confidence_score'), many=True)
        return Response(serializer.data)


class GetMuscleRecoveryStatusView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return MuscleRecovery.objects.filter(user=request.user).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        Get current recovery status for all muscle groups.
        Returns recovery status for ALL muscle groups - those in recovery and those fully recovered.
        """
        from exercise.models import Exercise
        all_muscle_groups = [choice[0] for choice in Exercise.MUSCLE_GROUPS]
        
        recovery_status = {}
        
        all_records = MuscleRecovery.objects.filter(
            user=request.user,
            muscle_group__in=all_muscle_groups
        ).select_related('source_workout').order_by(
            'muscle_group',
            '-source_workout__datetime',
            '-recovery_until'
        )
        
        seen_groups = set()
        recovery_records = {}
        for record in all_records:
            if record.muscle_group not in seen_groups:
                recovery_records[record.muscle_group] = record
                seen_groups.add(record.muscle_group)

        for muscle_group in all_muscle_groups:
            if muscle_group in recovery_records:
                record = recovery_records[muscle_group]
                record.update_recovery_status()
                recovery_status[muscle_group] = MuscleRecoverySerializer(record).data
            else:
                recovery_status[muscle_group] = {
                    'id': None,
                    'muscle_group': muscle_group,
                    'fatigue_score': 0.0,
                    'total_sets': 0,
                    'recovery_hours': 0,
                    'recovery_until': None,
                    'is_recovered': True,
                    'source_workout': None,
                    'hours_until_recovery': 0,
                    'recovery_percentage': 100,
                    'created_at': None,
                    'updated_at': None
                }
        
        cns_recovery = None
        if is_pro_user(request.user):
            cns_recovery_record = CNSRecovery.objects.filter(
                user=request.user
            ).select_related('source_workout').order_by('-recovery_until').first()
            
            if cns_recovery_record:
                cns_recovery_record.update_recovery_status()
                cns_recovery = CNSRecoverySerializer(cns_recovery_record).data
            else:
                cns_recovery = {
                    'id': None,
                    'cns_load': 0.0,
                    'recovery_hours': 0,
                    'recovery_until': None,
                    'is_recovered': True,
                    'source_workout': None,
                    'hours_until_recovery': 0,
                    'recovery_percentage': 100,
                    'created_at': None,
                    'updated_at': None
                }
        else:
            cns_recovery = None
        
        return Response({
            'recovery_status': recovery_status,
            'cns_recovery': cns_recovery,
            'is_pro': is_pro_user(request.user),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
