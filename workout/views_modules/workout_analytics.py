"""
Workout analytics and summary views.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Max, Sum, Avg, ExpressionWrapper, F, FloatField
from django.db.models.functions import Cast
from datetime import datetime, timedelta, date as date_type
from collections import defaultdict
from exercise.models import Exercise
from core.mixins import ConditionalGetMixin
from ..models import Workout, WorkoutExercise, WorkoutMuscleRecovery, ExerciseSet
from ..permissions import is_pro_user, get_pro_response


# --- Science-Based Volume Targets (Schoenfeld / Israetel MEV–MAV–MRV) ---
# Values: (min_sets_per_week, max_sets_per_week) for hypertrophy
WEEKLY_SET_TARGETS = {
    'chest':      (10, 20),
    'shoulders':  (16, 22),
    'biceps':     (14, 20),
    'triceps':    (10, 14),
    'forearms':   (10, 14),
    'lats':       (10, 20),
    'traps':      (12, 20),
    'lower_back': (6,  10),
    'quads':      (12, 20),
    'hamstrings': (10, 16),
    'glutes':     (4,  12),
    'calves':     (8,  16),
    'abs':        (16, 20),
    'obliques':   (0,  16),
    'abductors':  (0,  16),
    'adductors':  (0,  16),
}

# --- Antagonist Pair Definitions ---
# (muscle_a, muscle_b, max_imbalance_ratio, label)
ANTAGONIST_PAIRS = [
    ('chest',     'lats',       1.5,  'Push/Pull (Chest vs Lats)'),
    ('quads',     'hamstrings', 1.4,  'Knee (Quads vs Hamstrings)'),
    ('biceps',    'triceps',    1.5,  'Elbow (Biceps vs Triceps)'),
    ('shoulders', 'traps',      2.0,  'Shoulder (Anterior vs Posterior)'),
]


def _linear_regression(x_values, y_values):
    """Ordinary least squares slope and intercept. Returns (None, None) if < 2 points."""
    n = len(x_values)
    if n < 2:
        return None, None
    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n
    numerator   = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return 0.0, y_mean
    slope = numerator / denominator
    return slope, y_mean - slope * x_mean


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
        max_weeks_pro = 104  # 2 years hard cap

        try:
            weeks_back = int(weeks_back)
        except ValueError:
            weeks_back = 12

        if is_pro:
            weeks_back = min(weeks_back, max_weeks_pro)
        elif weeks_back > max_weeks_free:
            weeks_back = max_weeks_free
        
        if start_date_param and end_date_param:
            try:
                start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()

                if is_pro:
                    max_days = max_weeks_pro * 7
                else:
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
                active_weeks = len(volumes)
                avg_sets_per_week = round(total_sets / active_weeks, 1)
                target = WEEKLY_SET_TARGETS.get(muscle_group)
                if target:
                    target_min, target_max = target
                    if avg_sets_per_week < target_min:
                        vol_status = 'undertrained'
                        vol_msg = (
                            f'Averaging {avg_sets_per_week} sets/week. '
                            f'Aim for {target_min}–{target_max} sets for hypertrophy stimulus.'
                        )
                    elif avg_sets_per_week > target_max:
                        vol_status = 'overtrained'
                        vol_msg = (
                            f'Averaging {avg_sets_per_week} sets/week exceeds MRV of {target_max}. '
                            f'Consider a deload to manage recovery debt.'
                        )
                    else:
                        vol_status = 'optimal'
                        vol_msg = (
                            f'Averaging {avg_sets_per_week} sets/week — within the '
                            f'{target_min}–{target_max} hypertrophy sweet spot.'
                        )
                else:
                    target_min, target_max = None, None
                    vol_status = 'optimal'
                    vol_msg = 'No evidence-based target defined for this muscle group.'

                summary[muscle_group] = {
                    'average_volume_per_week': round(sum(volumes) / active_weeks, 2),
                    'max_volume_per_week':     round(max(volumes), 2),
                    'min_volume_per_week':     round(min(volumes), 2),
                    'total_weeks_trained':     active_weeks,
                    'total_sets':              total_sets,
                    'total_workouts':          total_workouts,
                    'sets_per_week':           avg_sets_per_week,
                    'target_min':              target_min,
                    'target_max':              target_max,
                    'volume_status':           vol_status,
                    'volume_status_message':   vol_msg,
                }
            else:
                target = WEEKLY_SET_TARGETS.get(muscle_group)
                target_min, target_max = target if target else (None, None)
                summary[muscle_group] = {
                    'average_volume_per_week': 0.0,
                    'max_volume_per_week':     0.0,
                    'min_volume_per_week':     0.0,
                    'total_weeks_trained':     0,
                    'total_sets':              0,
                    'total_workouts':          0,
                    'sets_per_week':           0.0,
                    'target_min':              target_min,
                    'target_max':              target_max,
                    'volume_status':           'untrained',
                    'volume_status_message':   (
                        f'No sets recorded. Aim for {target_min}–{target_max} sets/week.'
                        if target_min is not None
                        else 'No sets recorded for this muscle group.'
                    ),
                }
        
        # --- Feature 2: Antagonist Balance Analysis ---
        balance = {}
        for muscle_a, muscle_b, threshold, label in ANTAGONIST_PAIRS:
            sets_a = summary.get(muscle_a, {}).get('total_sets', 0)
            sets_b = summary.get(muscle_b, {}).get('total_sets', 0)

            if sets_a == 0 and sets_b == 0:
                balance[f'{muscle_a}_vs_{muscle_b}'] = {
                    'label':    label,
                    'sets_a':   sets_a,
                    'sets_b':   sets_b,
                    'muscle_a': muscle_a,
                    'muscle_b': muscle_b,
                    'ratio':    None,
                    'status':   'no_data',
                    'message':  f'No training data for {label}.',
                }
                continue

            if sets_b == 0:
                ratio = None
                is_imbalanced = True
                msg = (
                    f'You train {muscle_a} but have no {muscle_b} sets recorded. '
                    f'Add {muscle_b} work to prevent postural imbalance.'
                )
            elif sets_a == 0:
                ratio = None
                is_imbalanced = True
                msg = (
                    f'You train {muscle_b} but have no {muscle_a} sets recorded. '
                    f'Add {muscle_a} work to prevent postural imbalance.'
                )
            else:
                if sets_a >= sets_b:
                    ratio = round(sets_a / sets_b, 2)
                    dominant, weaker = muscle_a, muscle_b
                else:
                    ratio = round(sets_b / sets_a, 2)
                    dominant, weaker = muscle_b, muscle_a

                is_imbalanced = ratio > threshold
                if is_imbalanced:
                    msg = (
                        f'{dominant.capitalize()} dominates {weaker} at a {ratio:.1f}:1 ratio '
                        f'(threshold {threshold}:1). Increase {weaker} volume to restore balance.'
                    )
                else:
                    msg = (
                        f'{label} ratio is {ratio:.1f}:1 — within the balanced range '
                        f'(threshold {threshold}:1).'
                    )

            balance[f'{muscle_a}_vs_{muscle_b}'] = {
                'label':    label,
                'sets_a':   sets_a,
                'sets_b':   sets_b,
                'muscle_a': muscle_a,
                'muscle_b': muscle_b,
                'ratio':    ratio,
                'status':   'imbalanced' if is_imbalanced else 'balanced',
                'message':  msg,
            }

        return Response({
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_weeks': len(weeks_list)
            },
            'weeks':      weeks_list,
            'summary':    summary,
            'balance':    balance,
            'is_pro':     is_pro,
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

        Score (0-10) is built from two independent components:

        Recovery component (0-5 pts):
            Average pre-workout recovery % across all worked muscles, scaled to 0-5.
            Muscles with no recorded snapshot go to neutrals -- not assumed perfect.
            Missing all data -> neutral (2.5).

        Performance component (0-5 pts, PRO only):
            Average normalised 1RM change across exercises that have history.
            Changes within the noise band (-5 % to +3 %) are neutral -- daily
            strength variation of 2-5 % is normal and not meaningful signal.
            Only drops > 5 % count negative; gains > 3 % count positive.
            No history -> neutral (2.5).

        Non-PRO:  score = recovery_component x 2  (full 0-10 from recovery alone)
        PRO:      score = recovery_component + performance_component
        """
        try:
            workout = Workout.objects.get(id=workout_id, user=request.user)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)

        is_pro = is_pro_user(request.user)

        # Pre-workout recovery snapshots
        pre_recovery = WorkoutMuscleRecovery.objects.filter(workout=workout, condition='pre')
        pre_recovery_dict = {r.muscle_group: float(r.recovery_progress) for r in pre_recovery}

        workout_exercises = WorkoutExercise.objects.filter(workout=workout).select_related('exercise')

        muscles_worked = set()
        exercise_1rm_data = {}

        for workout_exercise in workout_exercises:
            exercise = workout_exercise.exercise
            if exercise.primary_muscle:
                muscles_worked.add(exercise.primary_muscle)
            if exercise.secondary_muscles:
                muscles_worked.update(m for m in exercise.secondary_muscles if m)
            if workout_exercise.one_rep_max:
                exercise_1rm_data[exercise.id] = {
                    'current_1rm': float(workout_exercise.one_rep_max),
                    'exercise_name': exercise.name,
                    'exercise_id': exercise.id,
                }

        positives = {}
        negatives = {}
        neutrals = {}

        # --- RECOVERY CATEGORISATION ---
        known_recovery_values = []
        for muscle in muscles_worked:
            if muscle in pre_recovery_dict:
                progress = pre_recovery_dict[muscle]
                known_recovery_values.append(progress)
                if progress >= 100.0:
                    positives[muscle] = {
                        'type': 'recovery',
                        'message': f'{muscle.capitalize()} was fully recovered before workout',
                        'pre_recovery': progress,
                    }
                elif progress < 70.0:
                    negatives[muscle] = {
                        'type': 'recovery',
                        'message': f'{muscle.capitalize()} was only {progress:.1f}% recovered before workout',
                        'pre_recovery': progress,
                    }
                else:
                    neutrals[muscle] = {
                        'type': 'recovery',
                        'message': f'{muscle.capitalize()} was {progress:.1f}% recovered before workout',
                        'pre_recovery': progress,
                    }
            else:
                # No snapshot recorded -- do not assume full recovery
                neutrals[muscle] = {
                    'type': 'recovery',
                    'message': f'{muscle.capitalize()}: No pre-workout recovery snapshot recorded',
                    'pre_recovery': None,
                }

        # Recovery score: average of muscles that have data, neutral when unknown
        if known_recovery_values:
            avg_recovery = sum(known_recovery_values) / len(known_recovery_values)
            recovery_score = (avg_recovery / 100.0) * 5.0
        else:
            recovery_score = 2.5  # no data -> neutral

        # --- 1RM PERFORMANCE CATEGORISATION (PRO only) ---
        performance_score = 2.5  # default neutral

        if is_pro and exercise_1rm_data:
            perf_deltas = []

            for exercise_id, data in exercise_1rm_data.items():
                current_1rm = data['current_1rm']
                exercise_name = data['exercise_name']

                previous = (
                    WorkoutExercise.objects
                    .filter(
                        exercise_id=exercise_id,
                        workout__user=request.user,
                        workout__is_done=True,
                        one_rep_max__isnull=False,
                    )
                    .exclude(workout=workout)
                    .order_by('-workout__datetime', '-workout__created_at')
                    .first()
                )

                if previous and previous.one_rep_max:
                    previous_1rm = float(previous.one_rep_max)
                    difference = current_1rm - previous_1rm
                    percent_change = (difference / previous_1rm) * 100 if previous_1rm > 0 else 0

                    if percent_change > 3.0:
                        # Meaningful PR -- above daily noise floor
                        positives[f'{exercise_name}_1rm'] = {
                            'type': '1rm',
                            'message': f'{exercise_name}: 1RM up {previous_1rm:.1f}->{current_1rm:.1f} kg (+{percent_change:.1f}%)',
                            'current_1rm': current_1rm,
                            'previous_1rm': previous_1rm,
                            'difference': difference,
                            'percent_change': round(percent_change, 1),
                        }
                        perf_deltas.append(1.0)
                    elif percent_change < -5.0:
                        # Meaningful regression -- beyond normal daily variation (2-5 %)
                        negatives[f'{exercise_name}_1rm'] = {
                            'type': '1rm',
                            'message': f'{exercise_name}: 1RM down {previous_1rm:.1f}->{current_1rm:.1f} kg ({percent_change:.1f}%)',
                            'current_1rm': current_1rm,
                            'previous_1rm': previous_1rm,
                            'difference': difference,
                            'percent_change': round(percent_change, 1),
                        }
                        perf_deltas.append(-1.0)
                    else:
                        # Within noise band (-5 % to +3 %) -- treat as maintained
                        neutrals[f'{exercise_name}_1rm'] = {
                            'type': '1rm',
                            'message': f'{exercise_name}: 1RM maintained at ~{current_1rm:.1f} kg ({percent_change:+.1f}%)',
                            'current_1rm': current_1rm,
                            'previous_1rm': previous_1rm,
                            'difference': difference,
                            'percent_change': round(percent_change, 1),
                        }
                        perf_deltas.append(0.0)
                else:
                    neutrals[f'{exercise_name}_1rm'] = {
                        'type': '1rm',
                        'message': f'{exercise_name}: No previous 1RM to compare',
                        'current_1rm': current_1rm,
                        'previous_1rm': None,
                        'difference': None,
                        'percent_change': None,
                    }

            if perf_deltas:
                avg_delta = sum(perf_deltas) / len(perf_deltas)  # -1 to +1
                performance_score = 2.5 + (avg_delta * 2.5)      # 0 to 5

        # --- FINAL SCORE (0-10) ---
        if is_pro:
            # Both components contribute equally (each 0-5 -> combined 0-10)
            score = recovery_score + performance_score
        else:
            # Non-PRO: scale recovery component to fill the full 0-10 range
            score = recovery_score * 2.0

        score = round(max(0.0, min(10.0, score)), 1)

        # --- Feature 4: Workout Diagnosis (Root Cause Analysis) ---
        has_pre_recovery_data = bool(pre_recovery_dict)

        fatigued_muscles = [
            muscle for muscle, data in negatives.items()
            if data.get('type') == 'recovery'
        ]
        performance_drop_exercises = [
            key for key, data in negatives.items()
            if data.get('type') == '1rm'
        ]

        if not has_pre_recovery_data:
            primary_issue = 'insufficient_data'
            diag_message = (
                'No pre-workout muscle recovery snapshot was recorded for this session. '
                'Start your workouts through the app to enable automatic recovery tracking.'
            )
            recommendation = (
                'Open the app before your next workout so recovery data is captured automatically.'
            )
        elif fatigued_muscles and score < 6.0:
            primary_issue = 'fatigue_accumulation'
            muscle_list = ', '.join(m.capitalize() for m in fatigued_muscles)
            diag_message = (
                f'{muscle_list} entered this session under-recovered (< 70%). '
                'Training fatigued muscles suppresses performance and increases injury risk.'
            )
            recommendation = (
                'Schedule an additional 24–48 h of rest for these muscles before training them again. '
                'Consider active recovery (walking, light cardio) rather than heavy loading.'
            )
        elif performance_drop_exercises and not fatigued_muscles:
            primary_issue = 'performance_drop'
            ex_list = ', '.join(
                negatives[k]['message'].split(':')[0]
                for k in performance_drop_exercises
            )
            diag_message = (
                f'1RM dropped > 5% on {ex_list} despite adequate muscle recovery. '
                'This points to systemic stressors rather than localised muscle fatigue.'
            )
            recommendation = (
                'Check sleep quality (aim for 7–9 h), hydration, and caloric intake. '
                'High life stress elevates cortisol and suppresses acute strength output.'
            )
        elif score >= 7.0:
            primary_issue = 'good_session'
            diag_message = (
                'Muscles were well-recovered and performance was maintained or improved. '
                'This is the ideal training state.'
            )
            recommendation = (
                'Maintain your current recovery schedule. '
                'Look for opportunities to add a small amount of load or volume next session.'
            )
        else:
            primary_issue = 'overreaching'
            diag_message = (
                'Session score is below 7 without a single dominant cause. '
                'This often reflects accumulated fatigue across multiple sessions.'
            )
            recommendation = (
                'Consider a deload week: reduce volume by 40–50% while maintaining intensity. '
                'Prioritise sleep and protein intake (1.6–2.2 g/kg body weight).'
            )

        diagnosis = {
            'primary_issue':  primary_issue,
            'message':        diag_message,
            'recommendation': recommendation,
        }

        return Response({
            'workout_id': workout.id,
            'score': score,
            'positives': positives,
            'negatives': negatives,
            'neutrals': neutrals,
            'summary': {
                'total_positives': len(positives),
                'total_negatives': len(negatives),
                'total_neutrals': len(neutrals),
                'muscles_worked': sorted(muscles_worked),
                'exercises_performed': len(exercise_1rm_data),
            },
            'diagnosis':            diagnosis,
            'is_pro':               is_pro,
            'has_advanced_insights': is_pro,
        }, status=status.HTTP_200_OK)


class UserStatsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return Workout.objects.filter(
            user=request.user, is_done=True
        ).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        """
        GET /api/workout/user-stats/
        Returns all meaningful lifetime and recent stats for the authenticated user.
        """
        user = request.user
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        month_start = today.replace(day=1)

        done_workouts = Workout.objects.filter(
            user=user, is_done=True, is_rest_day=False
        )

        # --- SESSIONS ---
        total_sessions = done_workouts.count()
        sessions_this_week = done_workouts.filter(datetime__date__gte=week_start).count()
        sessions_this_month = done_workouts.filter(datetime__date__gte=month_start).count()

        # --- STREAK ---
        training_dates = set(
            done_workouts.values_list('datetime__date', flat=True).distinct()
        )

        current_streak = 0
        check_date = today
        if check_date not in training_dates:
            check_date = today - timedelta(days=1)
        while check_date in training_dates:
            current_streak += 1
            check_date -= timedelta(days=1)

        longest_streak = 0
        if training_dates:
            sorted_dates = sorted(training_dates)
            run = 1
            for i in range(1, len(sorted_dates)):
                if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
                    run += 1
                    longest_streak = max(longest_streak, run)
                else:
                    run = 1
            longest_streak = max(longest_streak, run)

        # --- VOLUME (kg lifted = weight × reps, warmups excluded) ---
        base_sets = ExerciseSet.objects.filter(
            workout_exercise__workout__user=user,
            workout_exercise__workout__is_done=True,
            workout_exercise__workout__is_rest_day=False,
            is_warmup=False,
            reps__gt=0,
            weight__gt=0,
        )
        vol_expr = ExpressionWrapper(
            Cast('weight', FloatField()) * F('reps'),
            output_field=FloatField()
        )

        total_volume_kg = round(
            base_sets.aggregate(total=Sum(vol_expr))['total'] or 0.0, 1
        )
        volume_this_week = round(
            base_sets.filter(
                workout_exercise__workout__datetime__date__gte=week_start
            ).aggregate(total=Sum(vol_expr))['total'] or 0.0, 1
        )
        volume_this_month = round(
            base_sets.filter(
                workout_exercise__workout__datetime__date__gte=month_start
            ).aggregate(total=Sum(vol_expr))['total'] or 0.0, 1
        )

        # --- DURATION ---
        duration_agg = done_workouts.aggregate(total=Sum('duration'), avg=Avg('duration'))
        total_duration_minutes = round((duration_agg['total'] or 0) / 60, 1)
        avg_duration_minutes = round((duration_agg['avg'] or 0) / 60, 1)

        # --- CALORIES ---
        cal_agg = done_workouts.aggregate(total=Sum('calories_burned'))
        total_calories = round(float(cal_agg['total'] or 0), 1)
        calories_this_week = round(float(
            done_workouts.filter(datetime__date__gte=week_start)
            .aggregate(total=Sum('calories_burned'))['total'] or 0
        ), 1)
        calories_this_month = round(float(
            done_workouts.filter(datetime__date__gte=month_start)
            .aggregate(total=Sum('calories_burned'))['total'] or 0
        ), 1)

        # --- CONSISTENCY ---
        last_30_start = today - timedelta(days=29)
        active_days_last_30 = done_workouts.filter(
            datetime__date__gte=last_30_start
        ).values('datetime__date').distinct().count()

        sessions_last_8_weeks = done_workouts.filter(
            datetime__date__gte=today - timedelta(weeks=8)
        ).count()
        avg_sessions_per_week = round(sessions_last_8_weeks / 8, 1)

        return Response({
            'streak': {
                'current': current_streak,
                'longest': longest_streak,
            },
            'sessions': {
                'total': total_sessions,
                'this_week': sessions_this_week,
                'this_month': sessions_this_month,
            },
            'volume_kg': {
                'total': total_volume_kg,
                'this_week': volume_this_week,
                'this_month': volume_this_month,
            },
            'time': {
                'total_minutes': total_duration_minutes,
                'avg_per_session_minutes': avg_duration_minutes,
            },
            'calories': {
                'total': total_calories,
                'this_week': calories_this_week,
                'this_month': calories_this_month,
            },
            'consistency': {
                'active_days_last_30': active_days_last_30,
                'avg_sessions_per_week': avg_sessions_per_week,
            },
        }, status=status.HTTP_200_OK)


class OverloadTrendView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, exercise_id=None, **kwargs):
        return WorkoutExercise.objects.filter(
            exercise_id=exercise_id,
            workout__user=request.user,
            workout__is_done=True,
            one_rep_max__isnull=False,
        ).aggregate(Max('updated_at'))['updated_at__max']

    def get(self, request, exercise_id):
        """
        GET /api/workout/exercise/<exercise_id>/overload-trend/
        PRO only. Analyses the last 8 weeks of 1RM data for an exercise via
        linear regression and classifies the progression trend.
        """
        if not is_pro_user(request.user):
            return get_pro_response()

        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({'error': 'Exercise not found'}, status=status.HTTP_404_NOT_FOUND)

        eight_weeks_ago = timezone.now() - timedelta(weeks=8)

        qs = (
            WorkoutExercise.objects
            .filter(
                exercise_id=exercise_id,
                workout__user=request.user,
                workout__is_done=True,
                one_rep_max__isnull=False,
                workout__datetime__gte=eight_weeks_ago,
            )
            .select_related('workout')
            .order_by('workout__datetime')
        )

        data_points = [
            {
                'date':        we.workout.datetime.date().isoformat(),
                'one_rep_max': round(float(we.one_rep_max), 2),
            }
            for we in qs
        ]

        n = len(data_points)

        if n < 2:
            return Response({
                'exercise_id':    exercise_id,
                'exercise_name':  exercise.name,
                'trend':          'insufficient_data',
                'data_points':    data_points,
                'weeks_analyzed': 8,
                'change_kg':      None,
                'change_percent': None,
                'message': (
                    'Not enough data to detect a trend. '
                    'Log at least 2 sessions with this exercise in the past 8 weeks.'
                ),
            })

        base = date_type.fromisoformat(data_points[0]['date'])
        x_vals = [(date_type.fromisoformat(dp['date']) - base).days for dp in data_points]
        y_vals = [dp['one_rep_max'] for dp in data_points]

        slope, _ = _linear_regression(x_vals, y_vals)

        first_1rm = y_vals[0]
        last_1rm  = y_vals[-1]
        change_kg  = round(last_1rm - first_1rm, 2)
        change_pct = round((change_kg / first_1rm * 100) if first_1rm > 0 else 0.0, 1)

        if n >= 4 and abs(change_pct) < 1.0:
            trend = 'stagnating'
            message = (
                f'1RM has barely changed over the last {n} sessions '
                f'({change_pct:+.1f}%). Try a rep scheme or exercise variation change.'
            )
        elif slope is not None and slope > 0 and change_pct >= 1.0:
            trend = 'progressing'
            message = (
                f'Solid upward trend — {change_kg:+.1f} kg ({change_pct:+.1f}%) '
                f'over {n} sessions. Keep progressive overload consistent.'
            )
        elif slope is not None and slope < 0 and change_pct <= -1.0:
            trend = 'regressing'
            message = (
                f'1RM has declined {abs(change_kg):.1f} kg ({change_pct:.1f}%) over '
                f'{n} sessions. Review recovery, nutrition, and technique.'
            )
        else:
            trend = 'insufficient_data'
            message = (
                f'Only {n} data points available. '
                'Log more sessions to establish a reliable trend.'
            )

        return Response({
            'exercise_id':    exercise_id,
            'exercise_name':  exercise.name,
            'trend':          trend,
            'data_points':    data_points,
            'weeks_analyzed': 8,
            'change_kg':      change_kg,
            'change_percent': change_pct,
            'message':        message,
        }, status=status.HTTP_200_OK)
