"""
Workout views organized into logical modules.
All views are imported here and re-exported for backward compatibility.
"""

# Import all views from modules
from .workout_crud import (
    CreateWorkoutView,
    GetWorkoutView,
    GetActiveWorkoutView,
    UpdateWorkoutView,
    DeleteWorkoutView,
    CompleteWorkoutView,
    CheckPreviousWorkoutPerformedView,
    CheckWorkoutPerformedTodayView,
    TotalWorkoutsPerformedView,
    WorkoutPagination,
)

from .workout_exercises import (
    AddExerciseToWorkoutView,
    AddExerciseSetToWorkoutExerciseView,
    UpdateExerciseSetView,
    DeleteExerciseSetView,
    DeleteWorkoutExerciseView,
    UpdateExerciseOrderView,
)

from .workout_history import (
    GetExercise1RMHistoryView,
    GetExerciseSetHistoryView,
    GetExerciseLastWorkoutView,
    CalendarView,
    GetAvailableYearsView,
    CalendarStatsView,
)

from .workout_templates import (
    CreateTemplateWorkoutView,
    GetTemplateWorkoutsView,
    DeleteTemplateWorkoutView,
    StartTemplateWorkoutView,
)

from .workout_timer import (
    GetRestTimerStateView,
    StopRestTimerView,
    ResumeRestTimerView,
)

from .workout_recovery import (
    GetRecoveryRecommendationsView,
    GetRestPeriodRecommendationsView,
    GetTrainingFrequencyRecommendationsView,
    GetRelevantResearchView,
    GetMuscleRecoveryStatusView,
    SuggestNextExerciseView,
    ExerciseOptimizationCheckView,
)

from .workout_analytics import (
    VolumeAnalysisView,
    WorkoutSummaryView,
    UserStatsView,
    OverloadTrendView,
)

from .workout_programs import (
    CreateWorkoutProgramView,
    GetWorkoutProgramsView,
    GetWorkoutProgramView,
    UpdateWorkoutProgramView,
    DeleteWorkoutProgramView,
    ActivateWorkoutProgramView,
    DeactivateWorkoutProgramView,
    CurrentProgramDayView,
)

# Re-export everything
__all__ = [
    # CRUD
    'CreateWorkoutView',
    'GetWorkoutView',
    'GetActiveWorkoutView',
    'UpdateWorkoutView',
    'DeleteWorkoutView',
    'CompleteWorkoutView',
    'CheckPreviousWorkoutPerformedView',
    'CheckWorkoutPerformedTodayView',
    'TotalWorkoutsPerformedView',
    # Exercises
    'AddExerciseToWorkoutView',
    'AddExerciseSetToWorkoutExerciseView',
    'UpdateExerciseSetView',
    'DeleteExerciseSetView',
    'DeleteWorkoutExerciseView',
    'UpdateExerciseOrderView',
    # History
    'GetExercise1RMHistoryView',
    'GetExerciseSetHistoryView',
    'GetExerciseLastWorkoutView',
    'CalendarView',
    'GetAvailableYearsView',
    'CalendarStatsView',
    # Templates
    'CreateTemplateWorkoutView',
    'GetTemplateWorkoutsView',
    'DeleteTemplateWorkoutView',
    'StartTemplateWorkoutView',
    # Timer
    'GetRestTimerStateView',
    'StopRestTimerView',
    'ResumeRestTimerView',
    # Recovery
    'GetRecoveryRecommendationsView',
    'GetRestPeriodRecommendationsView',
    'GetTrainingFrequencyRecommendationsView',
    'GetRelevantResearchView',
    'GetMuscleRecoveryStatusView',
    'SuggestNextExerciseView',
    'ExerciseOptimizationCheckView',
    # Analytics
    'VolumeAnalysisView',
    'WorkoutSummaryView',
    'UserStatsView',
    'OverloadTrendView',
    # Programs
    'CreateWorkoutProgramView',
    'GetWorkoutProgramsView',
    'GetWorkoutProgramView',
    'UpdateWorkoutProgramView',
    'DeleteWorkoutProgramView',
    'ActivateWorkoutProgramView',
    'DeactivateWorkoutProgramView',
    'CurrentProgramDayView',
    # Pagination
    'WorkoutPagination',
]
