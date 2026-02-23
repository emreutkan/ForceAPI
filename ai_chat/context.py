import logging
from datetime import timedelta

from django.db.models import Sum, Avg, F, FloatField, Max, Count
from django.db.models.functions import Cast
from django.db.models import ExpressionWrapper
from django.utils import timezone
from django.core.cache import cache

from workout.models import (
    Workout, WorkoutExercise, ExerciseSet,
    MuscleRecovery, CNSRecovery,
)
from workout.utils import get_current_recovery_progress
from user.models import UserProfile

logger = logging.getLogger(__name__)

CONTEXT_CACHE_TTL = 300  # 5 minutes


def build_user_context(user):
    """
    Fetch all relevant user data and format it as text for the LLM system prompt.
    Cached per user for 5 minutes — stats don't change mid-conversation.
    """
    cache_key = f"ai_context:{user.pk}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    parts = []

    profile_section = _build_profile(user)
    if profile_section:
        parts.append(profile_section)

    # Check if user has ANY completed workouts
    has_workouts = Workout.objects.filter(user=user, is_done=True, is_rest_day=False).exists()

    if not has_workouts:
        parts.append(
            "## NO TRAINING DATA\n"
            "This user has no workout history yet. They are a new user.\n"
            "If they ask what to do: suggest starting with a Push/Pull/Legs, "
            "Upper/Lower, or Full Body split — whichever suits their schedule. "
            "Do NOT ask for data you already know you don't have. Just give a solid starting point."
        )
    else:
        stats_section = _build_training_stats(user)
        if stats_section:
            parts.append(stats_section)

        workouts_section = _build_recent_workouts(user)
        if workouts_section:
            parts.append(workouts_section)

        recovery_section = _build_recovery_status(user)
        if recovery_section:
            parts.append(recovery_section)

        exercises_section = _build_top_exercises(user)
        if exercises_section:
            parts.append(exercises_section)

    result = "\n\n".join(parts)
    cache.set(cache_key, result, CONTEXT_CACHE_TTL)
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_profile(user):
    try:
        profile = UserProfile.objects.get(user=user)
        weight = f"{profile.body_weight}kg" if profile.body_weight else "Not set"
        height = f"{profile.height}cm" if profile.height else "Not set"
    except UserProfile.DoesNotExist:
        weight = "Not set"
        height = "Not set"

    return (
        "## USER PROFILE\n"
        f"- Gender: {user.gender or 'Not set'}\n"
        f"- Height: {height}\n"
        f"- Weight: {weight}\n"
        f"- Member since: {user.created_at.strftime('%B %Y')}\n"
        f"- Subscription: {'Pro' if user.is_pro else 'Free'}"
    )


def _build_training_stats(user):
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    done = Workout.objects.filter(user=user, is_done=True, is_rest_day=False)
    total_sessions = done.count()
    if total_sessions == 0:
        return "## TRAINING STATS\nNo completed workouts yet."

    sessions_this_week = done.filter(datetime__date__gte=week_start).count()
    sessions_this_month = done.filter(datetime__date__gte=month_start).count()

    # Streak — only load last 60 days (not all-time)
    streak_cutoff = today - timedelta(days=60)
    training_dates = set(
        done.filter(datetime__date__gte=streak_cutoff)
        .values_list('datetime__date', flat=True).distinct()
    )
    current_streak = 0
    check = today
    if check not in training_dates:
        check = today - timedelta(days=1)
    while check in training_dates:
        current_streak += 1
        check -= timedelta(days=1)

    # Volume this week
    vol_expr = ExpressionWrapper(
        Cast('weight', FloatField()) * F('reps'),
        output_field=FloatField(),
    )
    base_sets = ExerciseSet.objects.filter(
        workout_exercise__workout__user=user,
        workout_exercise__workout__is_done=True,
        workout_exercise__workout__is_rest_day=False,
        is_warmup=False,
        reps__gt=0,
        weight__gt=0,
    )
    volume_this_week = round(
        base_sets.filter(
            workout_exercise__workout__datetime__date__gte=week_start,
        ).aggregate(total=Sum(vol_expr))['total'] or 0.0, 1
    )

    # Duration
    duration_agg = done.aggregate(avg=Avg('duration'))
    avg_duration_min = round((duration_agg['avg'] or 0) / 60, 1)

    # Consistency
    last_30_start = today - timedelta(days=29)
    active_days_30 = done.filter(
        datetime__date__gte=last_30_start,
    ).values('datetime__date').distinct().count()

    sessions_8w = done.filter(datetime__date__gte=today - timedelta(weeks=8)).count()
    avg_per_week = round(sessions_8w / 8, 1)

    return (
        "## TRAINING STATS\n"
        f"- Current streak: {current_streak} day(s)\n"
        f"- Sessions this week: {sessions_this_week}\n"
        f"- Sessions this month: {sessions_this_month}\n"
        f"- Total sessions: {total_sessions}\n"
        f"- Volume this week: {volume_this_week}kg\n"
        f"- Avg session duration: {avg_duration_min}min\n"
        f"- Active days (last 30): {active_days_30}\n"
        f"- Avg sessions/week (8-week): {avg_per_week}"
    )


def _build_recent_workouts(user):
    cutoff = timezone.now() - timedelta(days=14)
    workouts = list(
        Workout.objects.filter(user=user, is_done=True, is_rest_day=False, datetime__gte=cutoff)
        .prefetch_related('workoutexercise_set__exercise')
        .order_by('-datetime')[:10]
    )
    if not workouts:
        return None

    # Batch-fetch volume per workout in one SQL query
    workout_ids = [w.pk for w in workouts]
    vol_expr = ExpressionWrapper(
        Cast('weight', FloatField()) * F('reps'),
        output_field=FloatField(),
    )
    volume_by_workout = dict(
        ExerciseSet.objects.filter(
            workout_exercise__workout_id__in=workout_ids,
            is_warmup=False,
            reps__gt=0,
            weight__gt=0,
        ).values('workout_exercise__workout_id').annotate(
            total_vol=Sum(vol_expr),
        ).values_list('workout_exercise__workout_id', 'total_vol')
    )

    lines = []
    for w in workouts:
        exercises = w.workoutexercise_set.all()[:5]
        ex_names = [we.exercise.name for we in exercises]
        duration_min = round(w.duration / 60, 1) if w.duration else 0
        total_vol = round(volume_by_workout.get(w.pk, 0) or 0)

        lines.append(
            f"- {w.datetime.strftime('%b %d')}: {w.title} | "
            f"{duration_min}min | Vol: {total_vol}kg | "
            f"Exercises: {', '.join(ex_names)}"
        )

    return "## RECENT WORKOUTS (Last 14 days)\n" + "\n".join(lines)


def _build_recovery_status(user):
    recovery_progress = get_current_recovery_progress(user)

    ready = {mg: pct for mg, pct in recovery_progress.items() if pct >= 85.0}
    fatigued = {mg: pct for mg, pct in recovery_progress.items() if pct < 85.0}

    # CNS recovery
    cns_record = (
        CNSRecovery.objects.filter(user=user)
        .select_related('source_workout')
        .order_by('-recovery_until')
        .first()
    )
    cns_line = None
    if cns_record:
        cns_record.update_recovery_status()
        if not cns_record.is_recovered and cns_record.recovery_until:
            workout_time = cns_record.source_workout.datetime if cns_record.source_workout else cns_record.created_at
            total_dur = cns_record.recovery_until - workout_time
            elapsed = timezone.now() - workout_time
            if total_dur.total_seconds() > 0:
                pct = min(100.0, max(0.0, (elapsed.total_seconds() / total_dur.total_seconds()) * 100))
                cns_line = f"CNS: {round(pct)}% recovered (load was {cns_record.cns_load})"
            else:
                cns_line = "CNS: Fully recovered"
        else:
            cns_line = "CNS: Fully recovered"

    parts = ["## RECOVERY STATUS (use this to recommend what to train today)"]

    if cns_line:
        parts.append(cns_line)

    if ready:
        sorted_ready = sorted(ready.items(), key=lambda x: x[1], reverse=True)
        ready_lines = [f"- {mg}: {pct}%" for mg, pct in sorted_ready]
        parts.append("READY TO TRAIN (>=85% recovered):")
        parts.extend(ready_lines)

    if fatigued:
        sorted_fatigued = sorted(fatigued.items(), key=lambda x: x[1])
        fatigued_lines = [f"- {mg}: {pct}%" for mg, pct in sorted_fatigued]
        parts.append("DO NOT TRAIN (still fatigued):")
        parts.extend(fatigued_lines)

    if not fatigued and not ready:
        parts.append("All muscles fully recovered. User can train any muscle group.")

    return "\n".join(parts)


def _build_top_exercises(user):
    """Top 5 exercises by frequency with best 1RM."""
    top = (
        WorkoutExercise.objects.filter(
            workout__user=user,
            workout__is_done=True,
        )
        .values('exercise__name', 'exercise_id')
        .annotate(
            count=Count('id'),
            best_1rm=Max('one_rep_max'),
            last_used=Max('workout__datetime'),
        )
        .order_by('-count')[:5]
    )

    if not top:
        return None

    lines = []
    for e in top:
        rm = f"{e['best_1rm']}kg" if e['best_1rm'] else "N/A"
        last = e['last_used'].strftime('%b %d') if e['last_used'] else "N/A"
        lines.append(f"- {e['exercise__name']}: Best 1RM {rm} | Last used: {last}")

    return "## TOP EXERCISES\n" + "\n".join(lines)
