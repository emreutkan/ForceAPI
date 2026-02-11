from exercise.views import ExerciseListView, addExerciseToWorkoutView
from django.urls import path


urlpatterns = [
    path('list/', ExerciseListView.as_view(), name='exercise-list'),
    path('add/<int:workout_id>/', addExerciseToWorkoutView.as_view(), name='add-exercise-to-workout'),
]