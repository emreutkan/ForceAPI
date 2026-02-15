"""
Rest timer related views.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from core.mixins import ConditionalGetMixin
from ..models import Workout
from ..utils import get_rest_timer_state


class GetRestTimerStateView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        w = Workout.objects.filter(user=request.user, is_done=False).values_list("updated_at", flat=True).first()
        return w

    def get(self, request):
        """
        GET /api/workout/active/rest-timer/
        Returns rest timer state for user's active workout.
        """
        try:
            workout = Workout.objects.filter(
                user=request.user,
                is_done=False
            ).first()
            
            if not workout:
                return Response({
                    "last_set_timestamp": None,
                    "last_exercise_category": None,
                    "elapsed_seconds": 0,
                    "is_paused": False
                })
            
            state = get_rest_timer_state(workout)
            return Response(state)
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StopRestTimerView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        w = Workout.objects.filter(user=request.user, is_done=False).values_list("updated_at", flat=True).first()
        return w

    def get(self, request):
        """
        GET /api/workout/active/rest-timer/stop
        Halts/pauses the rest timer for the active workout.
        """
        try:
            workout = Workout.objects.filter(
                user=request.user,
                is_done=False
            ).first()
            
            if not workout:
                return Response({
                    'error': 'No active workout found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            if not workout.rest_timer_paused_at:
                workout.rest_timer_paused_at = timezone.now()
                workout.save(update_fields=['rest_timer_paused_at'])
            
            state = get_rest_timer_state(workout)
            return Response({
                'message': 'Rest timer paused',
                **state
            })
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ResumeRestTimerView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        w = Workout.objects.filter(user=request.user, is_done=False).values_list("updated_at", flat=True).first()
        return w

    def get(self, request):
        """
        GET /api/workout/active/rest-timer/resume
        Resumes/unpauses the rest timer for the active workout.
        """
        try:
            workout = Workout.objects.filter(
                user=request.user,
                is_done=False
            ).first()
            
            if not workout:
                return Response({
                    'error': 'No active workout found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            if workout.rest_timer_paused_at:
                workout.rest_timer_paused_at = None
                workout.save(update_fields=['rest_timer_paused_at'])
            
            state = get_rest_timer_state(workout)
            return Response({
                'message': 'Rest timer resumed',
                **state
            })
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
