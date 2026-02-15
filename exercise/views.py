from django.shortcuts import render
from rest_framework.views import APIView
from .models import Exercise
from .serializers import ExerciseSerializer
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from workout.models import Workout, WorkoutExercise
from django.core.cache import cache
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Max
from core.mixins import ConditionalGetMixin

class ExercisePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

class ExerciseListView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = ExercisePagination
    queryset = Exercise.objects.all()
    serializer_class = ExerciseSerializer

    def get_last_modified(self, request, **kwargs):
        return Exercise.objects.filter(is_active=True).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        query = request.query_params.get('search', None)
        cache_key = f'exercises_list_{query or "all"}'
        
        # Cache globally (same for all users) - exercises don't change per user
        exercises_data = cache.get(cache_key)
        if exercises_data is None:
            exercises = Exercise.objects.filter(is_active=True)
            if query:
                keywords = query.lower().split()
                for word in keywords:
                    # Search for word in name, primary_muscle or equipment_type
                    # Also handle simple plurals by stripping 's' from query word
                    q_obj = Q(name__icontains=word) | \
                            Q(primary_muscle__icontains=word) | \
                            Q(equipment_type__icontains=word)
                    
                    if word.endswith('s') and len(word) > 3:
                        singular = word[:-1]
                        q_obj |= Q(name__icontains=singular) | \
                                 Q(primary_muscle__icontains=singular) | \
                                 Q(equipment_type__icontains=singular)
                    
                    exercises = exercises.filter(q_obj)
            
            serializer = ExerciseSerializer(exercises, many=True)
            exercises_data = serializer.data
            cache.set(cache_key, exercises_data, 60*60)  # 1 hour cache
        
        return Response(exercises_data)
        
class addExerciseToWorkoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, workout_id):
        try:
            workout = Workout.objects.get(id=workout_id, user=request.user)
        except Workout.DoesNotExist:
            return Response({'error': 'Workout not found'}, status=status.HTTP_404_NOT_FOUND)
        exercise_id = request.data.get('exercise_id')
        order = request.data.get('order')
        if not order:
            exercises_in_workout = WorkoutExercise.objects.filter(workout=workout).count()
            order = exercises_in_workout + 1
        if not exercise_id:
            return Response({'error': 'exercise_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            exercise = Exercise.objects.get(id=exercise_id)
        except Exercise.DoesNotExist:
             return Response({'error': 'Exercise not found'}, status=status.HTTP_404_NOT_FOUND)

        # Fix: Create a WorkoutExercise object instead of workout.exercises.add()
        WorkoutExercise.objects.create(workout=workout, exercise=exercise, order=order)
        
        return Response(ExerciseSerializer(exercise).data, status=status.HTTP_200_OK)

