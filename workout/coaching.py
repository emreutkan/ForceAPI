"""
Deterministic workout coaching built only from logged workout data.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from exercise.models import Exercise

from .constants import (
    ACTIVE_SESSION_SET_CAP,
    CNS_BACKOFF_THRESHOLD,
    CNS_PUSH_THRESHOLD,
    COMPOUND_MIN_REST_SECONDS,
    ISOLATION_MIN_REST_SECONDS,
    LOW_RIR_WARNING,
    NO_PROGRAM_MUSCLE_PRIORITY,
    PERFORMANCE_IMPROVEMENT_PCT,
    PERFORMANCE_REGRESSION_PCT,
    PERFORMANCE_STAGNATION_BAND_PCT,
    PRIMARY_RECOVERY_SKIP,
    READY_TO_TRAIN_RECOVERY,
    REP_DROP_WARNING_PCT,
    SECONDARY_RECOVERY_SWAP,
    TOO_LITTLE_FREQUENCY_DAYS,
    WEEKLY_SET_TARGETS,
)
from .models import CNSRecovery, Workout, WorkoutExercise, WorkoutMuscleRecovery, WorkoutProgram
from .utils import get_current_recovery_progress


SEVERITY_RANK = {
    'error': 0,
    'warning': 1,
    'info': 2,
}

POSITIVE_CODES = {
    'strong_progress',
    'well_recovered_training',
    'balanced_volume',
    'productive_frequency',
    'undertrained_opportunity',
}


def _serialize_exercise_brief(exercise):
    return {
        'id': exercise.id,
        'name': exercise.name,
        'primary_muscle': exercise.primary_muscle,
        'secondary_muscles': [m for m in (exercise.secondary_muscles or []) if m],
        'category': exercise.category,
        'equipment_type': exercise.equipment_type,
    }


def _build_finding(code, severity, message, evidence=None):
    return {
        'code': code,
        'severity': severity,
        'message': message,
        'evidence': evidence or {},
    }


def _sort_findings(findings):
    return sorted(
        findings,
        key=lambda item: (
            SEVERITY_RANK.get(item['severity'], 99),
            item['code'],
            item['message'],
        )
    )


def _unique_findings(findings):
    unique = []
    seen = set()
    for finding in findings:
        evidence = finding.get('evidence') or {}
        key = (
            finding['code'],
            evidence.get('exercise_id'),
            evidence.get('workout_exercise_id'),
            evidence.get('muscle_group'),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return _sort_findings(unique)


def _calculate_recovery_percentage(record):
    if not record:
        return 100.0

    if record.is_recovered or not record.recovery_until:
        return 100.0

    workout_time = record.source_workout.datetime if record.source_workout else record.created_at
    total_duration = record.recovery_until - workout_time
    elapsed = timezone.now() - workout_time

    if total_duration.total_seconds() <= 0:
        return 100.0

    linear_progress = elapsed.total_seconds() / total_duration.total_seconds()
    if linear_progress <= 0.3:
        non_linear_progress = linear_progress * 0.7
    elif linear_progress <= 0.7:
        non_linear_progress = 0.21 + (linear_progress - 0.3) * 1.225
    else:
        non_linear_progress = 0.7 + (linear_progress - 0.7) * 1.0

    return round(min(100.0, max(0.0, non_linear_progress * 100)), 1)


def get_current_cns_recovery_percent(user):
    record = (
        CNSRecovery.objects
        .filter(user=user)
        .select_related('source_workout')
        .order_by('-recovery_until', '-created_at')
        .first()
    )
    if not record:
        return 100.0
    record.update_recovery_status()
    return _calculate_recovery_percentage(record)


def _get_pre_workout_recovery(workout):
    return {
        record.muscle_group: float(record.recovery_progress)
        for record in WorkoutMuscleRecovery.objects.filter(
            workout=workout,
            condition='pre',
        )
    }


def get_active_program_context(user):
    program = (
        WorkoutProgram.objects
        .filter(user=user, is_active=True)
        .prefetch_related('days__exercises__exercise')
        .first()
    )
    if not program:
        return None

    count_from = program.activated_at or program.created_at
    days_completed = Workout.objects.filter(
        user=user,
        is_done=True,
        datetime__gte=count_from,
    ).count()
    current_day_number = (days_completed % program.cycle_length) + 1
    current_day = program.days.filter(day_number=current_day_number).first()

    return {
        'program': program,
        'activated_at': count_from,
        'days_completed_since_activation': days_completed,
        'current_day_number': current_day_number,
        'current_day': current_day,
    }


def get_active_workout_muscle_sets(active_workout):
    counts = defaultdict(int)
    if not active_workout:
        return counts

    for workout_exercise in active_workout.workoutexercise_set.all():
        counts[workout_exercise.exercise.primary_muscle] += workout_exercise.sets.filter(
            is_warmup=False
        ).count()
    return counts


def get_weekly_muscle_set_load(user, reference_time=None, days=7):
    if reference_time is None:
        reference_time = timezone.now()

    cutoff = reference_time - timedelta(days=days)
    workouts = (
        Workout.objects
        .filter(
            user=user,
            is_done=True,
            is_rest_day=False,
            datetime__gte=cutoff,
            datetime__lte=reference_time,
        )
        .prefetch_related('workoutexercise_set__exercise', 'workoutexercise_set__sets')
    )

    counts = defaultdict(float)
    for workout in workouts:
        for workout_exercise in workout.workoutexercise_set.all():
            set_count = workout_exercise.sets.filter(is_warmup=False).count()
            if set_count == 0:
                continue

            primary = workout_exercise.exercise.primary_muscle
            counts[primary] += float(set_count)

            for secondary in workout_exercise.exercise.secondary_muscles or []:
                if secondary:
                    counts[secondary] += round(set_count * 0.5, 1)

    return {key: round(value, 1) for key, value in counts.items()}


def get_days_since_last_trained(user, reference_time=None):
    if reference_time is None:
        reference_time = timezone.now()

    values = {
        choice[0]: None
        for choice in Exercise.MUSCLE_GROUPS
    }

    exercises = (
        WorkoutExercise.objects
        .filter(
            workout__user=user,
            workout__is_done=True,
            workout__is_rest_day=False,
            workout__datetime__lte=reference_time,
        )
        .select_related('workout', 'exercise')
        .order_by('-workout__datetime', '-id')
    )

    for workout_exercise in exercises:
        primary = workout_exercise.exercise.primary_muscle
        if values.get(primary) is not None:
            continue
        delta = reference_time.date() - workout_exercise.workout.datetime.date()
        values[primary] = delta.days
        if all(value is not None for value in values.values()):
            break

    return values


def get_exercise_session_proxies(workout_exercise):
    working_sets = list(workout_exercise.sets.filter(is_warmup=False).order_by('set_number'))
    if not working_sets:
        return {
            'set_count': 0,
            'avg_rir': None,
            'avg_rest_seconds': None,
            'rep_drop_pct': None,
        }

    first_reps = working_sets[0].reps or 0
    last_reps = working_sets[-1].reps or 0
    rep_drop_pct = None
    if len(working_sets) >= 2 and first_reps > 0:
        rep_drop_pct = round(((first_reps - last_reps) / first_reps) * 100, 1)

    avg_rir = sum((exercise_set.reps_in_reserve or 0) for exercise_set in working_sets) / len(working_sets)
    avg_rest = sum((exercise_set.rest_time_before_set or 0) for exercise_set in working_sets) / len(working_sets)

    return {
        'set_count': len(working_sets),
        'avg_rir': round(avg_rir, 2),
        'avg_rest_seconds': round(avg_rest, 1),
        'rep_drop_pct': rep_drop_pct,
    }


def get_latest_completed_exposure(user, exercise_id):
    return (
        WorkoutExercise.objects
        .filter(
            exercise_id=exercise_id,
            workout__user=user,
            workout__is_done=True,
            one_rep_max__isnull=False,
        )
        .select_related('workout', 'exercise')
        .prefetch_related('sets')
        .order_by('-workout__datetime', '-id')
        .first()
    )


def get_exercise_performance_snapshot(user, exercise_id, current_workout_exercise=None, reference_time=None):
    history = []
    current_point = None

    if current_workout_exercise and current_workout_exercise.one_rep_max is not None:
        current_point = {
            'workout_exercise_id': current_workout_exercise.id,
            'date': current_workout_exercise.workout.datetime.date().isoformat(),
            'one_rep_max': float(current_workout_exercise.one_rep_max),
        }
        if reference_time is None:
            reference_time = current_workout_exercise.workout.datetime

    qs = (
        WorkoutExercise.objects
        .filter(
            exercise_id=exercise_id,
            workout__user=user,
            workout__is_done=True,
            one_rep_max__isnull=False,
        )
        .select_related('workout')
        .order_by('-workout__datetime', '-id')
    )

    if reference_time is not None:
        qs = qs.filter(workout__datetime__lt=reference_time)

    if current_workout_exercise is not None:
        qs = qs.exclude(id=current_workout_exercise.id)

    history = [
        {
            'workout_exercise_id': workout_exercise.id,
            'date': workout_exercise.workout.datetime.date().isoformat(),
            'one_rep_max': float(workout_exercise.one_rep_max),
        }
        for workout_exercise in qs[:3]
    ]

    series = []
    if current_point is not None:
        series.append(current_point)
    series.extend(history)

    if current_point is None:
        series = history

    if len(series) < 2:
        return {
            'status': 'insufficient_data',
            'current_1rm': series[0]['one_rep_max'] if series else None,
            'previous_1rm': None,
            'change_percent': None,
            'sample_size': len(series),
            'data_points': series,
        }

    current_1rm = series[0]['one_rep_max']
    previous_1rm = series[1]['one_rep_max']
    change_percent = round(((current_1rm - previous_1rm) / previous_1rm) * 100, 1) if previous_1rm > 0 else 0.0

    if change_percent <= PERFORMANCE_REGRESSION_PCT:
        status = 'regressing'
    elif change_percent >= PERFORMANCE_IMPROVEMENT_PCT:
        status = 'progressing'
    elif len(series) >= 3:
        oldest = series[-1]['one_rep_max']
        span_change = round(((current_1rm - oldest) / oldest) * 100, 1) if oldest > 0 else 0.0
        if abs(span_change) < PERFORMANCE_STAGNATION_BAND_PCT:
            status = 'stagnating'
        else:
            status = 'maintained'
    else:
        status = 'maintained'

    return {
        'status': status,
        'current_1rm': current_1rm,
        'previous_1rm': previous_1rm,
        'change_percent': change_percent,
        'sample_size': len(series),
        'data_points': series,
    }


def _pick_exercise_candidates_for_muscle(user, muscle_group, blocked_secondaries=None, exclude_exercise_id=None):
    blocked_secondaries = set(blocked_secondaries or [])
    usage_counts = dict(
        WorkoutExercise.objects
        .filter(
            workout__user=user,
            exercise__primary_muscle=muscle_group,
        )
        .values('exercise_id')
        .annotate(total=Count('id'))
        .values_list('exercise_id', 'total')
    )

    candidates = []
    for exercise in Exercise.objects.filter(primary_muscle=muscle_group, is_active=True):
        if exclude_exercise_id and exercise.id == exclude_exercise_id:
            continue
        secondaries = {muscle for muscle in (exercise.secondary_muscles or []) if muscle}
        blocked_overlap = len(secondaries & blocked_secondaries)
        candidates.append(
            (
                blocked_overlap,
                0 if exercise.category == 'isolation' else 1,
                -(usage_counts.get(exercise.id, 0)),
                exercise.name.lower(),
                exercise,
            )
        )

    candidates.sort(key=lambda item: item[:4])
    return [item[4] for item in candidates]


def pick_swap_exercise(user, exercise, recovery_map):
    blocked_secondaries = [
        muscle
        for muscle in (exercise.secondary_muscles or [])
        if muscle and recovery_map.get(muscle, 100.0) < SECONDARY_RECOVERY_SWAP
    ]
    if not blocked_secondaries:
        return None

    candidates = _pick_exercise_candidates_for_muscle(
        user,
        exercise.primary_muscle,
        blocked_secondaries=blocked_secondaries,
        exclude_exercise_id=exercise.id,
    )
    return candidates[0] if candidates else None


def pick_no_program_exercise(user, muscle_group):
    candidates = _pick_exercise_candidates_for_muscle(user, muscle_group)
    return candidates[0] if candidates else None


def evaluate_exercise_action(
    user,
    exercise,
    recovery_map,
    weekly_sets,
    days_since_last,
    cns_recovery,
    active_sets_by_muscle=None,
    planned_sets=3,
    current_workout_exercise=None,
):
    active_sets_by_muscle = active_sets_by_muscle or {}
    planned_sets = planned_sets or 3
    primary = exercise.primary_muscle
    secondaries = [muscle for muscle in (exercise.secondary_muscles or []) if muscle]
    primary_recovery = recovery_map.get(primary, 100.0)
    blocked_secondaries = [
        muscle
        for muscle in secondaries
        if recovery_map.get(muscle, 100.0) < SECONDARY_RECOVERY_SWAP
    ]
    in_session_sets = active_sets_by_muscle.get(primary, 0)
    weekly_primary_sets = weekly_sets.get(primary, 0.0)
    target_min, target_max = WEEKLY_SET_TARGETS.get(primary, (0, 999))
    performance = get_exercise_performance_snapshot(
        user,
        exercise.id,
        current_workout_exercise=current_workout_exercise,
        reference_time=current_workout_exercise.workout.datetime if current_workout_exercise else None,
    )
    latest_exposure = get_latest_completed_exposure(user, exercise.id)
    exposure_source = current_workout_exercise or latest_exposure
    exposure_proxies = get_exercise_session_proxies(exposure_source) if exposure_source else None

    findings = []
    action = 'hold'
    load_delta_pct = 0.0
    set_delta = 0
    reason_codes = []
    swap_exercise = None

    if primary_recovery < PRIMARY_RECOVERY_SKIP:
        action = 'skip'
        set_delta = -planned_sets
        reason_codes.append('under_recovered')
        findings.append(
            _build_finding(
                'under_recovered',
                'error',
                f'{primary.replace("_", " ").capitalize()} is only {primary_recovery:.0f}% recovered, so this exercise should be skipped today.',
                {
                    'exercise_id': exercise.id,
                    'muscle_group': primary,
                    'recovery_percent': primary_recovery,
                },
            )
        )

    if in_session_sets >= ACTIVE_SESSION_SET_CAP:
        action = 'skip'
        set_delta = min(set_delta, -1) if set_delta else -1
        reason_codes.append('too_much_volume')
        findings.append(
            _build_finding(
                'too_much_volume',
                'error',
                f'{primary.replace("_", " ").capitalize()} already has {in_session_sets} working sets in this session.',
                {
                    'exercise_id': exercise.id,
                    'muscle_group': primary,
                    'working_sets_logged': in_session_sets,
                },
            )
        )

    if action != 'skip' and blocked_secondaries:
        action = 'swap'
        reason_codes.append('poor_exercise_selection')
        swap_exercise = pick_swap_exercise(user, exercise, recovery_map)
        findings.append(
            _build_finding(
                'poor_exercise_selection',
                'warning',
                f'{exercise.name} leans on under-recovered secondary muscles and should be swapped today.',
                {
                    'exercise_id': exercise.id,
                    'muscle_group': primary,
                    'blocked_secondary_muscles': blocked_secondaries,
                    'swap_exercise_id': swap_exercise.id if swap_exercise else None,
                },
            )
        )

    if action not in {'skip', 'swap'} and cns_recovery < CNS_BACKOFF_THRESHOLD and exercise.category == 'compound':
        action = 'backoff'
        load_delta_pct = -5.0
        set_delta = -1 if planned_sets > 2 else 0
        reason_codes.append('cns_fatigue')
        findings.append(
            _build_finding(
                'cns_fatigue',
                'warning',
                f'CNS recovery is only {cns_recovery:.0f}%, so compound loading should be backed off.',
                {
                    'exercise_id': exercise.id,
                    'cns_recovery_percent': cns_recovery,
                },
            )
        )

    if action not in {'skip', 'swap'} and performance['status'] == 'regressing':
        action = 'backoff'
        load_delta_pct = min(load_delta_pct, -5.0)
        set_delta = -1 if planned_sets > 2 else set_delta
        reason_codes.append('regressing_exercise')
        findings.append(
            _build_finding(
                'regressing_exercise',
                'warning',
                f'{exercise.name} is down {performance["change_percent"]:.1f}% versus its previous exposure.',
                {
                    'exercise_id': exercise.id,
                    'change_percent': performance['change_percent'],
                    'current_1rm': performance['current_1rm'],
                    'previous_1rm': performance['previous_1rm'],
                },
            )
        )

    if action not in {'skip', 'swap'} and performance['status'] == 'progressing':
        if primary_recovery >= READY_TO_TRAIN_RECOVERY and cns_recovery >= CNS_PUSH_THRESHOLD and weekly_primary_sets <= target_max:
            action = 'push'
            load_delta_pct = 2.5
            reason_codes.append('progressing_exercise')
            findings.append(
                _build_finding(
                    'strong_progress',
                    'info',
                    f'{exercise.name} is trending up and is ready for a small progression.',
                    {
                        'exercise_id': exercise.id,
                        'change_percent': performance['change_percent'],
                        'recovery_percent': primary_recovery,
                    },
                )
            )

    if action not in {'skip', 'swap'} and performance['status'] == 'stagnating':
        reason_codes.append('stagnating_exercise')
        findings.append(
            _build_finding(
                'stagnating_exercise',
                'warning',
                f'{exercise.name} has been flat across recent logged exposures.',
                {
                    'exercise_id': exercise.id,
                    'data_points': performance['data_points'],
                },
            )
        )

    if action not in {'skip', 'swap'} and exposure_proxies:
        avg_rir = exposure_proxies.get('avg_rir')
        avg_rest_seconds = exposure_proxies.get('avg_rest_seconds')
        rep_drop_pct = exposure_proxies.get('rep_drop_pct')
        minimum_rest = COMPOUND_MIN_REST_SECONDS if exercise.category == 'compound' else ISOLATION_MIN_REST_SECONDS

        if avg_rir is not None and rep_drop_pct is not None and avg_rir <= LOW_RIR_WARNING and rep_drop_pct >= REP_DROP_WARNING_PCT:
            action = 'backoff'
            load_delta_pct = min(load_delta_pct, -5.0)
            set_delta = -1 if planned_sets > 2 else set_delta
            reason_codes.append('too_much_intensity')
            findings.append(
                _build_finding(
                    'too_much_intensity',
                    'warning',
                    f'{exercise.name} showed heavy fatigue spillover in the last exposure.',
                    {
                        'exercise_id': exercise.id,
                        'avg_rir': avg_rir,
                        'rep_drop_pct': rep_drop_pct,
                    },
                )
            )

        if avg_rest_seconds is not None and rep_drop_pct is not None and avg_rest_seconds < minimum_rest and rep_drop_pct >= REP_DROP_WARNING_PCT:
            reason_codes.append('insufficient_rest')
            findings.append(
                _build_finding(
                    'insufficient_rest',
                    'warning',
                    f'{exercise.name} is showing a large rep drop while rest stays below {minimum_rest} seconds.',
                    {
                        'exercise_id': exercise.id,
                        'avg_rest_seconds': avg_rest_seconds,
                        'rep_drop_pct': rep_drop_pct,
                    },
                )
            )

    if action not in {'skip', 'swap'} and weekly_primary_sets > target_max:
        if action == 'push':
            action = 'hold'
            load_delta_pct = 0.0
        elif action == 'hold':
            action = 'backoff'
            load_delta_pct = -5.0
            set_delta = -1 if planned_sets > 2 else 0
        reason_codes.append('too_much_weekly_volume')
        findings.append(
            _build_finding(
                'too_much_volume',
                'warning',
                f'{primary.replace("_", " ").capitalize()} is already above its recent weekly set target.',
                {
                    'exercise_id': exercise.id,
                    'muscle_group': primary,
                    'weekly_sets': weekly_primary_sets,
                    'target_max': target_max,
                },
            )
        )

    days_gap = days_since_last.get(primary)
    if days_gap is not None and days_gap > TOO_LITTLE_FREQUENCY_DAYS:
        reason_codes.append('too_little_frequency')
        findings.append(
            _build_finding(
                'too_little_frequency',
                'warning',
                f'{primary.replace("_", " ").capitalize()} has not been trained in {days_gap} days.',
                {
                    'exercise_id': exercise.id,
                    'muscle_group': primary,
                    'days_since_last_trained': days_gap,
                },
            )
        )

    if action not in {'skip', 'swap'} and weekly_primary_sets < target_min and primary_recovery >= READY_TO_TRAIN_RECOVERY:
        findings.append(
            _build_finding(
                'undertrained_opportunity',
                'info',
                f'{primary.replace("_", " ").capitalize()} is fresh and below its weekly set target.',
                {
                    'exercise_id': exercise.id,
                    'muscle_group': primary,
                    'weekly_sets': weekly_primary_sets,
                    'target_min': target_min,
                },
            )
        )

    if performance['status'] == 'insufficient_data':
        reason_codes.append('insufficient_data')
        findings.append(
            _build_finding(
                'insufficient_data',
                'info',
                f'{exercise.name} does not have enough logged history yet, so the coach is staying conservative.',
                {
                    'exercise_id': exercise.id,
                    'sample_size': performance['sample_size'],
                },
            )
        )

    if (
        action == 'hold'
        and primary_recovery >= READY_TO_TRAIN_RECOVERY
        and target_min <= weekly_primary_sets <= target_max
    ):
        findings.append(
            _build_finding(
                'balanced_volume',
                'info',
                f'{primary.replace("_", " ").capitalize()} is in a good recovery and volume window.',
                {
                    'exercise_id': exercise.id,
                    'muscle_group': primary,
                    'weekly_sets': weekly_primary_sets,
                    'recovery_percent': primary_recovery,
                },
            )
        )

    return {
        'exercise_id': exercise.id,
        'exercise': _serialize_exercise_brief(exercise),
        'action': action,
        'load_delta_pct': load_delta_pct,
        'set_delta': set_delta,
        'reason_codes': sorted(set(reason_codes)),
        'swap_exercise': _serialize_exercise_brief(swap_exercise) if swap_exercise else None,
        'evidence': {
            'primary_recovery_percent': primary_recovery,
            'secondary_recovery_percents': {
                muscle: recovery_map.get(muscle, 100.0)
                for muscle in secondaries
            },
            'weekly_sets': weekly_primary_sets,
            'weekly_target_min': target_min,
            'weekly_target_max': target_max,
            'days_since_last_trained': days_gap,
            'in_session_sets': in_session_sets,
            'cns_recovery_percent': cns_recovery,
            'performance': performance,
            'latest_exposure_proxies': exposure_proxies,
        },
        'findings': _unique_findings(findings),
        'workout_exercise_id': current_workout_exercise.id if current_workout_exercise else None,
    }


def _build_change_recommendations(findings):
    recommendations = []
    seen = set()
    for finding in findings:
        code = finding['code']
        evidence = finding.get('evidence') or {}
        if code == 'under_recovered':
            message = 'Wait for the primary muscle to recover before repeating this slot.'
        elif code == 'too_much_volume':
            message = 'Cut 1-2 sets or stop adding more work for that muscle in the same session.'
        elif code == 'poor_exercise_selection':
            message = 'Swap to a cleaner variation that keeps under-recovered secondary muscles out.'
        elif code == 'regressing_exercise':
            message = 'Back off load slightly and rebuild quality reps before pushing again.'
        elif code == 'stagnating_exercise':
            message = 'Repeat the lift without adding load until performance clearly moves again.'
        elif code == 'too_little_frequency':
            message = 'Bring that muscle back sooner in the week instead of leaving long gaps.'
        elif code == 'too_much_intensity':
            message = 'Stop taking every set too close to failure if rep quality is collapsing.'
        elif code == 'insufficient_rest':
            message = 'Take longer rest periods so reps stay stable across sets.'
        else:
            continue

        key = (code, evidence.get('exercise_id'), evidence.get('muscle_group'))
        if key in seen:
            continue
        seen.add(key)
        recommendations.append({
            'code': code,
            'message': message,
        })
    return recommendations


def _session_decision_from_actions(actions):
    if not actions:
        return 'delay_day'

    blocked = sum(1 for action in actions if action['action'] == 'skip')
    modifications = sum(1 for action in actions if action['action'] in {'skip', 'swap', 'backoff'})

    if blocked * 2 >= len(actions):
        return 'delay_day'
    if modifications:
        return 'train_with_modifications'
    return 'train'


def build_workout_coach_review(user, workout):
    workout_exercises = list(
        workout.workoutexercise_set.select_related('exercise').prefetch_related('sets').all()
    )
    pre_recovery = _get_pre_workout_recovery(workout)
    weekly_before = get_weekly_muscle_set_load(user, reference_time=workout.datetime)
    days_since_before = get_days_since_last_trained(user, reference_time=workout.datetime - timedelta(seconds=1))
    cns_recovery = get_current_cns_recovery_percent(user)

    findings = []
    exercise_actions = []
    primary_set_counts = defaultdict(int)

    for workout_exercise in workout_exercises:
        primary_set_counts[workout_exercise.exercise.primary_muscle] += workout_exercise.sets.filter(
            is_warmup=False
        ).count()

    if not pre_recovery:
        findings.append(
            _build_finding(
                'insufficient_data',
                'warning',
                'No pre-workout recovery snapshot was recorded for this session, so the coach has limited recovery evidence.',
                {'workout_id': workout.id},
            )
        )

    for workout_exercise in workout_exercises:
        exercise = workout_exercise.exercise
        action = evaluate_exercise_action(
            user=user,
            exercise=exercise,
            recovery_map=pre_recovery or get_current_recovery_progress(user),
            weekly_sets=weekly_before,
            days_since_last=days_since_before,
            cns_recovery=cns_recovery,
            active_sets_by_muscle={exercise.primary_muscle: primary_set_counts[exercise.primary_muscle]},
            planned_sets=primary_set_counts[exercise.primary_muscle] or 3,
            current_workout_exercise=workout_exercise,
        )
        action['workout_exercise_id'] = workout_exercise.id
        action['evidence']['pre_recovery_percent'] = pre_recovery.get(exercise.primary_muscle)
        exercise_actions.append(action)
        findings.extend(action['findings'])

        if pre_recovery.get(exercise.primary_muscle, 100.0) >= READY_TO_TRAIN_RECOVERY:
            findings.append(
                _build_finding(
                    'well_recovered_training',
                    'info',
                    f'{exercise.primary_muscle.replace("_", " ").capitalize()} started this session in a good recovery state.',
                    {
                        'exercise_id': exercise.id,
                        'muscle_group': exercise.primary_muscle,
                        'recovery_percent': pre_recovery.get(exercise.primary_muscle),
                    },
                )
            )

    findings = _unique_findings(findings)
    what_went_wrong = [finding for finding in findings if finding['code'] not in POSITIVE_CODES and finding['severity'] != 'info']
    what_went_right = [finding for finding in findings if finding['code'] in POSITIVE_CODES]
    if not what_went_wrong and not what_went_right:
        what_went_right = [finding for finding in findings if finding['severity'] == 'info']

    return {
        'workout_id': workout.id,
        'session_decision': _session_decision_from_actions(exercise_actions),
        'findings': findings,
        'exercise_actions': exercise_actions,
        'what_went_wrong': what_went_wrong,
        'what_went_right': what_went_right,
        'what_to_change_next_time': _build_change_recommendations(findings),
        'summary': {
            'finding_count': len(findings),
            'issue_count': len(what_went_wrong),
            'positive_count': len(what_went_right),
        },
    }


def _build_program_day_payload(program_context):
    current_day = program_context['current_day']
    if not current_day:
        return None
    return {
        'id': current_day.id,
        'day_number': current_day.day_number,
        'name': current_day.name,
        'is_rest_day': current_day.is_rest_day,
        'exercises': [
            {
                'id': exercise.id,
                'order': exercise.order,
                'target_sets': exercise.target_sets,
                'exercise': _serialize_exercise_brief(exercise.exercise),
            }
            for exercise in current_day.exercises.all()
        ],
    }


def build_next_workout_coach(user):
    recovery_map = get_current_recovery_progress(user)
    weekly_sets = get_weekly_muscle_set_load(user)
    days_since_last = get_days_since_last_trained(user)
    cns_recovery = get_current_cns_recovery_percent(user)
    active_workout = (
        Workout.objects
        .filter(user=user, is_done=False)
        .prefetch_related('workoutexercise_set__exercise', 'workoutexercise_set__sets')
        .first()
    )
    active_sets = get_active_workout_muscle_sets(active_workout)

    findings = []
    exercise_actions = []
    program_context = get_active_program_context(user)

    if program_context and program_context['current_day']:
        current_day = program_context['current_day']
        if current_day.is_rest_day:
            findings.append(
                _build_finding(
                    'scheduled_rest_day',
                    'info',
                    'Your active program marks today as a rest day, so the coach is not forcing a training session.',
                    {
                        'program_id': program_context['program'].id,
                        'day_number': current_day.day_number,
                    },
                )
            )
            return {
                'session_decision': 'delay_day',
                'findings': findings,
                'exercise_actions': [],
                'program': {
                    'id': program_context['program'].id,
                    'name': program_context['program'].name,
                    'cycle_length': program_context['program'].cycle_length,
                    'days_completed_since_activation': program_context['days_completed_since_activation'],
                    'current_day': _build_program_day_payload(program_context),
                },
                'active_workout_id': active_workout.id if active_workout else None,
            }

        for program_exercise in current_day.exercises.all():
            action = evaluate_exercise_action(
                user=user,
                exercise=program_exercise.exercise,
                recovery_map=recovery_map,
                weekly_sets=weekly_sets,
                days_since_last=days_since_last,
                cns_recovery=cns_recovery,
                active_sets_by_muscle=active_sets,
                planned_sets=program_exercise.target_sets,
            )
            action['planned_sets'] = program_exercise.target_sets
            exercise_actions.append(action)
            findings.extend(action['findings'])

        findings = _unique_findings(findings)
        return {
            'session_decision': _session_decision_from_actions(exercise_actions),
            'findings': findings,
            'exercise_actions': exercise_actions,
            'program': {
                'id': program_context['program'].id,
                'name': program_context['program'].name,
                'cycle_length': program_context['program'].cycle_length,
                'days_completed_since_activation': program_context['days_completed_since_activation'],
                'current_day': _build_program_day_payload(program_context),
            },
            'active_workout_id': active_workout.id if active_workout else None,
        }

    priority_map = {muscle: idx for idx, muscle in enumerate(NO_PROGRAM_MUSCLE_PRIORITY)}
    target_muscles = []
    total_completed = Workout.objects.filter(user=user, is_done=True, is_rest_day=False).count()

    for muscle_group, _label in Exercise.MUSCLE_GROUPS:
        recovery = recovery_map.get(muscle_group, 100.0)
        if recovery < READY_TO_TRAIN_RECOVERY:
            continue

        weekly = weekly_sets.get(muscle_group, 0.0)
        target_min, _target_max = WEEKLY_SET_TARGETS.get(muscle_group, (0, 999))
        deficit = max(0.0, target_min - weekly)
        days_gap = days_since_last.get(muscle_group)
        if total_completed < 3 and muscle_group not in priority_map:
            continue
        target_muscles.append(
            (
                -deficit,
                -(days_gap or 0),
                priority_map.get(muscle_group, 999),
                muscle_group,
            )
        )

    target_muscles.sort()
    for _deficit, _days_gap, _priority, muscle_group in target_muscles[:4]:
        exercise = pick_no_program_exercise(user, muscle_group)
        if not exercise:
            continue
        action = evaluate_exercise_action(
            user=user,
            exercise=exercise,
            recovery_map=recovery_map,
            weekly_sets=weekly_sets,
            days_since_last=days_since_last,
            cns_recovery=cns_recovery,
            active_sets_by_muscle=active_sets,
            planned_sets=3,
        )
        exercise_actions.append(action)
        findings.extend(action['findings'])

    if not exercise_actions:
        findings.append(
            _build_finding(
                'under_recovered',
                'warning',
                'No good training slot is clearly available from the current workout data, so the coach recommends waiting.',
                {},
            )
        )

    findings = _unique_findings(findings)
    if any(finding['code'] == 'insufficient_data' for finding in findings):
        findings = _unique_findings(findings + [
            _build_finding(
                'insufficient_data',
                'info',
                'Workout history is still sparse, so recommendations stay conservative until more sessions are logged.',
                {},
            )
        ])

    return {
        'session_decision': _session_decision_from_actions(exercise_actions) if exercise_actions else 'delay_day',
        'findings': findings,
        'exercise_actions': exercise_actions,
        'program': None,
        'active_workout_id': active_workout.id if active_workout else None,
    }


def build_active_muscle_suggestions(user, active_workout):
    recovery_map = get_current_recovery_progress(user)
    weekly_sets = get_weekly_muscle_set_load(user)
    active_sets = get_active_workout_muscle_sets(active_workout)
    suggestions = []

    priority_map = {muscle: idx for idx, muscle in enumerate(NO_PROGRAM_MUSCLE_PRIORITY)}
    for muscle_group, _label in Exercise.MUSCLE_GROUPS:
        recovery = recovery_map.get(muscle_group, 100.0)
        working_sets = active_sets.get(muscle_group, 0)
        if recovery < SECONDARY_RECOVERY_SWAP or working_sets >= ACTIVE_SESSION_SET_CAP:
            continue

        weekly = weekly_sets.get(muscle_group, 0.0)
        target_min, _target_max = WEEKLY_SET_TARGETS.get(muscle_group, (0, 999))
        deficit = round(max(0.0, target_min - weekly), 1)
        suggested_exercise = pick_no_program_exercise(user, muscle_group)
        suggestions.append(
            {
                'muscle_group': muscle_group,
                'recovery_percent': recovery,
                'already_in_workout': muscle_group in active_sets,
                'working_sets_logged': working_sets,
                'weekly_set_deficit': deficit,
                'priority_rank': priority_map.get(muscle_group, 999),
                'suggested_exercise': _serialize_exercise_brief(suggested_exercise) if suggested_exercise else None,
            }
        )

    suggestions.sort(
        key=lambda item: (
            item['working_sets_logged'] >= ACTIVE_SESSION_SET_CAP,
            -item['weekly_set_deficit'],
            -item['recovery_percent'],
            item['priority_rank'],
        )
    )
    return suggestions


def build_active_workout_coach(user):
    active_workout = (
        Workout.objects
        .filter(user=user, is_done=False)
        .prefetch_related('workoutexercise_set__exercise', 'workoutexercise_set__sets')
        .first()
    )

    if not active_workout:
        return {
            'active_workout': None,
            'session_decision': 'delay_day',
            'live_decision': 'stop',
            'findings': [],
            'exercise_actions': [],
            'suggestions': [],
        }

    recovery_map = get_current_recovery_progress(user)
    weekly_sets = get_weekly_muscle_set_load(user)
    days_since_last = get_days_since_last_trained(user)
    cns_recovery = get_current_cns_recovery_percent(user)
    active_sets = get_active_workout_muscle_sets(active_workout)

    findings = []
    exercise_actions = []
    for workout_exercise in active_workout.workoutexercise_set.all():
        action = evaluate_exercise_action(
            user=user,
            exercise=workout_exercise.exercise,
            recovery_map=recovery_map,
            weekly_sets=weekly_sets,
            days_since_last=days_since_last,
            cns_recovery=cns_recovery,
            active_sets_by_muscle=active_sets,
            planned_sets=max(active_sets.get(workout_exercise.exercise.primary_muscle, 0), 1),
            current_workout_exercise=workout_exercise,
        )
        action['workout_exercise_id'] = workout_exercise.id
        exercise_actions.append(action)
        findings.extend(action['findings'])

    findings = _unique_findings(findings)
    suggestions = build_active_muscle_suggestions(user, active_workout)
    session_decision = _session_decision_from_actions(exercise_actions)

    if session_decision == 'train':
        live_decision = 'continue'
    elif session_decision == 'train_with_modifications':
        live_decision = 'switch'
    else:
        live_decision = 'stop'

    return {
        'active_workout': {
            'id': active_workout.id,
            'title': active_workout.title,
            'exercise_count': active_workout.workoutexercise_set.count(),
        },
        'session_decision': session_decision,
        'live_decision': live_decision,
        'findings': findings,
        'exercise_actions': exercise_actions,
        'suggestions': suggestions,
    }


def build_exercise_optimization_payload(user, workout_exercise):
    active_workout = (
        Workout.objects
        .filter(id=workout_exercise.workout_id, user=user, is_done=False)
        .prefetch_related('workoutexercise_set__exercise', 'workoutexercise_set__sets')
        .first()
    )
    if not active_workout:
        return {
            'overall_status': 'recommended',
            'warnings': [],
            'coach': None,
        }

    coach = build_active_workout_coach(user)
    action = next(
        (
            item for item in coach['exercise_actions']
            if item.get('workout_exercise_id') == workout_exercise.id
        ),
        None,
    )
    if not action:
        return {
            'overall_status': 'recommended',
            'warnings': [],
            'coach': coach,
        }

    warnings = []
    for finding in action['findings']:
        if finding['code'] in POSITIVE_CODES or finding['severity'] == 'info':
            continue
        evidence = finding.get('evidence') or {}
        recommendation = _build_change_recommendations([finding])
        warnings.append(
            {
                'type': finding['code'],
                'severity': finding['severity'],
                'muscle': evidence.get('muscle_group'),
                'recovery_percent': evidence.get('recovery_percent'),
                'sets_already_done': evidence.get('working_sets_logged'),
                'message': finding['message'],
                'recommendation': recommendation[0]['message'] if recommendation else None,
            }
        )

    overall_status = 'recommended'
    if any(item['severity'] == 'error' for item in warnings):
        overall_status = 'not_recommended'
    elif any(item['severity'] == 'warning' for item in warnings):
        overall_status = 'caution'

    return {
        'overall_status': overall_status,
        'warnings': warnings,
        'coach': coach,
    }
