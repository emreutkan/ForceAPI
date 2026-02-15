from django.urls import path
from .views import CreateWorkoutView, AddExerciseToWorkoutView, AddExerciseSetToWorkoutExerciseView, GetWorkoutView, GetActiveWorkoutView, DeleteExerciseSetView, DeleteWorkoutExerciseView, UpdateExerciseOrderView, CompleteWorkoutView, DeleteWorkoutView, CheckPreviousWorkoutPerformedView, CheckWorkoutPerformedTodayView, CreateTemplateWorkoutView, GetTemplateWorkoutsView, StartTemplateWorkoutView, DeleteTemplateWorkoutView, UpdateWorkoutView, UpdateExerciseSetView, GetRestTimerStateView, StopRestTimerView, ResumeRestTimerView, CalendarView, GetAvailableYearsView, CalendarStatsView, GetExercise1RMHistoryView, GetExerciseSetHistoryView, GetExerciseLastWorkoutView, GetRecoveryRecommendationsView, GetRestPeriodRecommendationsView, GetTrainingFrequencyRecommendationsView, GetRelevantResearchView, GetMuscleRecoveryStatusView, VolumeAnalysisView, WorkoutSummaryView
urlpatterns = [
    path('create/', CreateWorkoutView.as_view(), name='create-workout'),
    path('list/', GetWorkoutView.as_view(), name='list-workouts'),
    path('<int:workout_id>/add_exercise/', AddExerciseToWorkoutView.as_view(), name='add-exercise'),
    path('exercise/<int:workout_exercise_id>/add_set/', AddExerciseSetToWorkoutExerciseView.as_view(), name='add-set'),
    path('active/', GetActiveWorkoutView.as_view(), name='get-active-workout'),
    path('active/rest-timer/', GetRestTimerStateView.as_view(), name='rest-timer-state'),
    path('active/rest-timer/stop/', StopRestTimerView.as_view(), name='stop-rest-timer'),
    path('active/rest-timer/resume/', ResumeRestTimerView.as_view(), name='resume-rest-timer'),
    path('list/<int:workout_id>/', GetWorkoutView.as_view(), name='get-workout'),
    # Calendar endpoints
    path('calendar/', CalendarView.as_view(), name='calendar-view'),
    path('calendar/stats/', CalendarStatsView.as_view(), name='calendar-stats'),
    path('years/', GetAvailableYearsView.as_view(), name='available-years'),
    # Exercise History endpoints
    path('exercise/<int:exercise_id>/1rm-history/', GetExercise1RMHistoryView.as_view(), name='exercise-1rm-history'),
    path('exercise/<int:exercise_id>/set-history/', GetExerciseSetHistoryView.as_view(), name='exercise-set-history'),
    path('exercise/<int:exercise_id>/last-workout/', GetExerciseLastWorkoutView.as_view(), name='exercise-last-workout'),
    # Training recommendations endpoints
    path('recommendations/recovery/', GetRecoveryRecommendationsView.as_view(), name='recovery-recommendations'),
    path('exercise/<int:workout_exercise_id>/rest-recommendations/', GetRestPeriodRecommendationsView.as_view(), name='rest-recommendations'),
    path('recommendations/frequency/', GetTrainingFrequencyRecommendationsView.as_view(), name='frequency-recommendations'),
    path('research/', GetRelevantResearchView.as_view(), name='relevant-research'),
    path('recovery/status/', GetMuscleRecoveryStatusView.as_view(), name='muscle-recovery-status'),
    path('volume-analysis/', VolumeAnalysisView.as_view(), name='volume-analysis'),
    path('set/<int:set_id>/update/', UpdateExerciseSetView.as_view(), name='update-set'),
    path('set/<int:set_id>/delete/', DeleteExerciseSetView.as_view(), name='delete-set'),
    path('exercise/<int:workout_exercise_id>/delete/', DeleteWorkoutExerciseView.as_view(), name='delete-workout-exercise'),
    # Changed from exercise/<id>/update_order to <workout_id>/update_order because the view expects workout_id
    path('<int:workout_id>/update_order/', UpdateExerciseOrderView.as_view(), name='update-exercise-order'),
    path('<int:workout_id>/update/', UpdateWorkoutView.as_view(), name='update-workout'),
    path('<int:workout_id>/complete/', CompleteWorkoutView.as_view(), name='complete-workout'),
    path('<int:workout_id>/summary/', WorkoutSummaryView.as_view(), name='workout-summary'),
    path('<int:workout_id>/delete/', DeleteWorkoutView.as_view(), name='delete-workout'),
    path('check-today/', CheckWorkoutPerformedTodayView.as_view(), name='check-workout-performed-today'),
    path('check-date/', CheckPreviousWorkoutPerformedView.as_view(), name='check-workout-performed-date'),
    # Template workout endpoints
    path('template/create/', CreateTemplateWorkoutView.as_view(), name='create-template-workout'),
    path('template/list/', GetTemplateWorkoutsView.as_view(), name='list-template-workouts'),
    path('template/delete/<int:template_id>/', DeleteTemplateWorkoutView.as_view(), name='delete-template-workout'),
    path('template/start/', StartTemplateWorkoutView.as_view(), name='start-template-workout'),
]
