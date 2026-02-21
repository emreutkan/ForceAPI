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


def _get_muscle_recovery_pct(user, muscle_group):
    """
    Return the current recovery percentage (0-100) for a muscle group.
    Returns 100 if no record exists (never trained = fully recovered).
    """
    record = (
        MuscleRecovery.objects
        .filter(user=user, muscle_group=muscle_group)
        .select_related('source_workout')
        .order_by('-source_workout__datetime', '-recovery_until')
        .first()
    )
    if not record:
        return 100.0

    record.update_recovery_status()

    if record.is_recovered:
        return 100.0

    # Reproduce the J-curve from MuscleRecoverySerializer
    if not record.recovery_until:
        return 100.0

    workout_time = record.source_workout.datetime if record.source_workout else record.created_at
    total_duration = record.recovery_until - workout_time
    elapsed = timezone.now() - workout_time

    if total_duration.total_seconds() <= 0:
        return 100.0

    linear_progress = elapsed.total_seconds() / total_duration.total_seconds()

    if linear_progress <= 0.3:
        non_linear = linear_progress * 0.7
    elif linear_progress <= 0.7:
        non_linear = 0.21 + (linear_progress - 0.3) * 1.225
    else:
        non_linear = 0.7 + (linear_progress - 0.7) * 1.0

    return min(100.0, max(0.0, round(non_linear * 100, 1)))


def _count_working_sets_in_active_workout(active_workout, muscle_group):
    """
    Count non-warmup sets already logged in the *current active (incomplete)*
    workout for a specific muscle group (primary only).
    """
    from exercise.models import Exercise as ExerciseModel
    count = 0
    for we in active_workout.workoutexercise_set.select_related('exercise').prefetch_related('sets').all():
        if we.exercise.primary_muscle == muscle_group:
            count += we.sets.filter(is_warmup=False).count()
    return count


class SuggestNextExerciseView(APIView):
    """
    GET /api/workout/active/suggest-exercise/

    Returns ordered muscle-group suggestions for the current active workout,
    ranked by recovery percentage (highest first).

    Rules:
    - Only suggest muscles >= 80% recovered.
    - Never suggest a muscle that is already worked in the active workout
      AND has >= 4 non-warmup sets logged (it's done for today).
    - Muscles with no MuscleRecovery record are treated as 100% recovered.
    - Muscles already in the active workout but with < 4 sets are included
      so the user can add more sets — they are flagged with
      already_in_workout=True.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from exercise.models import Exercise as ExerciseModel

        # ── Active workout ────────────────────────────────────────────────
        active_workout = Workout.objects.filter(
            user=request.user, is_done=False
        ).prefetch_related(
            'workoutexercise_set__exercise',
            'workoutexercise_set__sets',
        ).first()

        # Muscles already in the active workout + their working-set count
        muscles_in_workout = {}  # muscle_group -> working_set_count
        if active_workout:
            for we in active_workout.workoutexercise_set.all():
                mg = we.exercise.primary_muscle
                if mg not in muscles_in_workout:
                    muscles_in_workout[mg] = 0
                muscles_in_workout[mg] += we.sets.filter(is_warmup=False).count()

        all_muscle_groups = [choice[0] for choice in ExerciseModel.MUSCLE_GROUPS]

        suggestions = []
        for muscle_group in all_muscle_groups:
            set_count = muscles_in_workout.get(muscle_group, 0)

            # Skip: already has 4+ working sets in the active workout
            if set_count >= 4:
                continue

            pct = _get_muscle_recovery_pct(request.user, muscle_group)

            # Only suggest muscles that are >= 80% recovered
            if pct < 80.0:
                continue

            suggestions.append({
                'muscle_group':      muscle_group,
                'recovery_percent':  pct,
                'already_in_workout': muscle_group in muscles_in_workout,
                'working_sets_logged': set_count,
            })

        # Sort: fully recovered (100%) first, then by descending recovery %
        suggestions.sort(key=lambda x: x['recovery_percent'], reverse=True)

        return Response({
            'suggestions':     suggestions,
            'has_active_workout': active_workout is not None,
        }, status=status.HTTP_200_OK)


class ExerciseOptimizationCheckView(APIView):
    """
    GET /api/workout/exercise/<workout_exercise_id>/optimization-check/

    Called immediately after a user adds an exercise to their active workout.
    Returns recovery and volume warnings for:

    1. Primary muscle recovery  (red warning if < 70%)
    2. Secondary muscle recovery  (yellow warning if any secondary < 70-80%)
    3. In-workout set volume for the primary muscle
       - 2–3 working sets already logged  → semi-warning (48h recovery risk)
       - 4+  working sets already logged  → hard warning (stop, no benefit)

    No PRO gate — shown to all users in real-time while building a workout.
    """
    permission_classes = [IsAuthenticated]

    # Thresholds
    PRIMARY_HARD_STOP  = 70.0   # < 70 % → do not train
    SECONDARY_WARN     = 80.0   # < 80 % → soft warning on secondary
    SETS_SEMI_WARN     = 2      # 2-3 sets already done → caution
    SETS_HARD_WARN     = 4      # 4+ sets already done  → stop

    def get(self, request, workout_exercise_id):
        # ── Load the workout exercise ──────────────────────────────────────
        try:
            workout_exercise = (
                WorkoutExercise.objects
                .select_related('exercise', 'workout')
                .get(id=workout_exercise_id, workout__user=request.user)
            )
        except WorkoutExercise.DoesNotExist:
            return Response(
                {'error': 'Workout exercise not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        exercise = workout_exercise.exercise
        workout  = workout_exercise.workout

        primary  = exercise.primary_muscle
        secondaries = [m for m in (exercise.secondary_muscles or []) if m]

        # ── Recovery checks ───────────────────────────────────────────────
        primary_pct = _get_muscle_recovery_pct(request.user, primary)

        secondary_results = []
        for sec in secondaries:
            sec_pct = _get_muscle_recovery_pct(request.user, sec)
            secondary_results.append({
                'muscle_group':      sec,
                'recovery_percent':  sec_pct,
            })

        # ── In-workout working-set count for the PRIMARY muscle ───────────
        # Count across ALL exercises in this workout that target the primary muscle
        sets_in_workout = 0
        for we in workout.workoutexercise_set.select_related('exercise').prefetch_related('sets').all():
            if we.exercise.primary_muscle == primary:
                sets_in_workout += we.sets.filter(is_warmup=False).count()

        # ── Build warnings ────────────────────────────────────────────────
        warnings = []

        # 1. Primary recovery
        if primary_pct < self.PRIMARY_HARD_STOP:
            warnings.append({
                'type':     'primary_not_recovered',
                'severity': 'error',
                'muscle':   primary,
                'recovery_percent': primary_pct,
                'message': (
                    f'{primary.replace("_", " ").capitalize()} is only {primary_pct:.0f}% recovered. '
                    'Training an under-recovered muscle significantly increases injury risk and '
                    'produces less stimulus than waiting for full recovery.'
                ),
                'recommendation': (
                    f'Wait until {primary.replace("_", " ").capitalize()} reaches at least 70% recovery '
                    'before training it again. Choose a different muscle group today.'
                ),
            })

        # 2. Secondary muscles
        for sec in secondary_results:
            if sec['recovery_percent'] < self.SECONDARY_WARN:
                # Find a primary-only alternative hint
                warnings.append({
                    'type':     'secondary_not_recovered',
                    'severity': 'warning',
                    'muscle':   sec['muscle_group'],
                    'recovery_percent': sec['recovery_percent'],
                    'message': (
                        f'{sec["muscle_group"].replace("_", " ").capitalize()} '
                        f'({sec["recovery_percent"]:.0f}% recovered) is a secondary muscle for '
                        f'{exercise.name}. This exercise will stress it before it\'s fully ready.'
                    ),
                    'recommendation': (
                        f'If you want to train {primary.replace("_", " ").capitalize()} today, '
                        f'consider an isolation exercise that targets {primary.replace("_", " ").capitalize()} '
                        f'without involving {sec["muscle_group"].replace("_", " ").capitalize()}.'
                    ),
                })

        # 3. In-workout volume
        if sets_in_workout >= self.SETS_HARD_WARN:
            warnings.append({
                'type':     'excessive_volume',
                'severity': 'error',
                'muscle':   primary,
                'sets_already_done': sets_in_workout,
                'message': (
                    f'You have already logged {sets_in_workout} working sets for '
                    f'{primary.replace("_", " ").capitalize()} this session. '
                    'Additional sets provide no meaningful extra stimulus and extend recovery time '
                    'well beyond 48 hours.'
                ),
                'recommendation': (
                    f'Stop training {primary.replace("_", " ").capitalize()} today. '
                    'More sets at this point only accumulate fatigue without adding growth signal.'
                ),
            })
        elif sets_in_workout >= self.SETS_SEMI_WARN:
            warnings.append({
                'type':     'high_volume',
                'severity': 'warning',
                'muscle':   primary,
                'sets_already_done': sets_in_workout,
                'message': (
                    f'You already have {sets_in_workout} working sets for '
                    f'{primary.replace("_", " ").capitalize()} this session. '
                    'Adding more will push recovery time beyond 48 hours, '
                    'making it harder to train this muscle again before the week ends.'
                ),
                'recommendation': (
                    'Limit to 1–2 more sets maximum, then move to a different muscle group.'
                ),
            })

        # ── Overall status ────────────────────────────────────────────────
        has_errors   = any(w['severity'] == 'error'   for w in warnings)
        has_warnings = any(w['severity'] == 'warning' for w in warnings)

        if has_errors:
            overall_status = 'not_recommended'
        elif has_warnings:
            overall_status = 'proceed_with_caution'
        else:
            overall_status = 'optimal'

        return Response({
            'workout_exercise_id': workout_exercise_id,
            'exercise': {
                'id':              exercise.id,
                'name':            exercise.name,
                'primary_muscle':  primary,
                'secondary_muscles': secondaries,
                'category':        exercise.category,
            },
            'primary_recovery': {
                'muscle_group':     primary,
                'recovery_percent': primary_pct,
            },
            'secondary_recovery': secondary_results,
            'sets_in_workout':   sets_in_workout,
            'overall_status':    overall_status,
            'warnings':          warnings,
        }, status=status.HTTP_200_OK)
