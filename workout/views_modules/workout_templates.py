"""
Template workout views.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Max
from core.mixins import ConditionalGetMixin
from ..models import Workout, WorkoutExercise, TemplateWorkout, TemplateWorkoutExercise
from ..serializers import CreateTemplateWorkoutSerializer, GetTemplateWorkoutSerializer, GetWorkoutSerializer


class CreateTemplateWorkoutView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = CreateTemplateWorkoutSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            template_workout = serializer.save()
            response_serializer = GetTemplateWorkoutSerializer(template_workout)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetTemplateWorkoutsView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return TemplateWorkout.objects.filter(user=request.user).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        template_workouts = TemplateWorkout.objects.filter(user=request.user).order_by('-created_at')
        serializer = GetTemplateWorkoutSerializer(template_workouts, many=True)
        return Response(serializer.data)


class DeleteTemplateWorkoutView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, template_id):
        try:
            template = TemplateWorkout.objects.get(id=template_id, user=request.user)
            template.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TemplateWorkout.DoesNotExist:
            return Response({'error': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)


class StartTemplateWorkoutView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        template_workout_id = request.data.get('template_workout_id')
        
        if not template_workout_id:
            return Response({'error': 'template_workout_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            template_workout = TemplateWorkout.objects.get(id=template_workout_id, user=request.user)
        except TemplateWorkout.DoesNotExist:
            return Response({'error': 'Template workout not found'}, status=status.HTTP_404_NOT_FOUND)
        
        active_workout = Workout.objects.filter(user=request.user, is_done=False).first()
        if active_workout:
            return Response({
                'error': 'ACTIVE_WORKOUT_EXISTS',
                'active_workout': active_workout.id,
                'message': 'Cannot start a new workout. Complete or delete the existing active workout first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        workout = Workout.objects.create(
            user=request.user,
            title=template_workout.title,
            is_done=False,
            notes=template_workout.notes
        )
        
        template_exercises = TemplateWorkoutExercise.objects.filter(
            template_workout=template_workout
        ).order_by('order')
        
        for template_exercise in template_exercises:
            WorkoutExercise.objects.create(
                workout=workout,
                exercise=template_exercise.exercise,
                order=template_exercise.order
            )
        
        serializer = GetWorkoutSerializer(workout)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
