from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404


from ..models import WorkoutProgram, Workout
from ..serializers import (
    CreateWorkoutProgramSerializer,
    WorkoutProgramSerializer,
    WorkoutProgramDaySerializer,
    UpdateWorkoutProgramSerializer,
)


class CreateWorkoutProgramView(APIView):
    permission_classes = [IsAuthenticated]
    """
    POST /api/workout/program/create/

    Create a new workout split program with its days and exercises.

    Request body:
    {
        "name": "My PPL Program",
        "cycle_length": 4,
        "days": [
            {
                "day_number": 1,
                "name": "Push Day",
                "is_rest_day": false,
                "exercises": [
                    {"exercise_id": 1, "target_sets": 3},
                    {"exercise_id": 2, "target_sets": 2}
                ]
            },
            {
                "day_number": 2,
                "name": "Pull Day",
                "is_rest_day": false,
                "exercises": [
                    {"exercise_id": 3, "target_sets": 4}
                ]
            },
            {
                "day_number": 3,
                "name": "Legs Day",
                "is_rest_day": false,
                "exercises": []
            },
            {
                "day_number": 4,
                "name": "Rest",
                "is_rest_day": true,
                "exercises": []
            }
        ]
    }
    """

    @transaction.atomic
    def post(self, request):
        serializer = CreateWorkoutProgramSerializer(
            data=request.data,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        program = serializer.save()
        return Response(
            WorkoutProgramSerializer(program).data,
            status=status.HTTP_201_CREATED,
        )


class GetWorkoutProgramsView(APIView):
    """
    GET /api/workout/program/list/

    Returns all workout programs for the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        programs = WorkoutProgram.objects.filter(user=request.user).prefetch_related(
            'days__exercises__exercise',
        )
        serializer = WorkoutProgramSerializer(programs, many=True)
        return Response(serializer.data)


class GetWorkoutProgramView(APIView):
    """
    GET /api/workout/program/<id>/

    Returns a single workout program.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, program_id):
        program = get_object_or_404(WorkoutProgram, id=program_id, user=request.user)
        serializer = WorkoutProgramSerializer(program)
        return Response(serializer.data)


class UpdateWorkoutProgramView(APIView):
    """
    PATCH /api/workout/program/<id>/update/

    Rename a workout program.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, program_id):
        program = get_object_or_404(WorkoutProgram, id=program_id, user=request.user)
        serializer = UpdateWorkoutProgramSerializer(program, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(WorkoutProgramSerializer(program).data)


class DeleteWorkoutProgramView(APIView):
    """
    DELETE /api/workout/program/<id>/delete/

    Delete a workout program and all its days/exercises.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, program_id):
        program = get_object_or_404(WorkoutProgram, id=program_id, user=request.user)
        program.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivateWorkoutProgramView(APIView):
    """
    POST /api/workout/program/<id>/activate/

    Set a program as the user's active split.
    Deactivates any previously active program.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, program_id):
        program = get_object_or_404(WorkoutProgram, id=program_id, user=request.user)
        program.activate()
        return Response(WorkoutProgramSerializer(program).data)


class DeactivateWorkoutProgramView(APIView):
    """
    POST /api/workout/program/<id>/deactivate/

    Deactivate the program without activating another one.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, program_id):
        program = get_object_or_404(WorkoutProgram, id=program_id, user=request.user)
        program.is_active = False
        program.save(update_fields=['is_active'])
        return Response(WorkoutProgramSerializer(program).data)


class CurrentProgramDayView(APIView):
    """
    GET /api/workout/program/current-day/

    Returns which day in the active program's cycle the user is on today,
    based on how many workout days (training + rest) they have logged since
    the program was activated.

    Response shape:
    {
        "program_id": 3,
        "program_name": "PPL Program",
        "cycle_length": 4,
        "days_completed_since_activation": 5,
        "current_day_number": 2,          // 1-indexed position in the cycle
        "current_day": {
            "id": 12,
            "day_number": 2,
            "name": "Pull Day",
            "is_rest_day": false,
            "exercises": [...]
        }
    }

    Returns 404 if the user has no active program.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Find the active program
        program = WorkoutProgram.objects.filter(
            user=request.user, is_active=True
        ).prefetch_related('days__exercises__exercise').first()

        if not program:
            return Response(
                {'error': 'NO_ACTIVE_PROGRAM', 'message': 'No active workout program found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. Determine when to start counting from.
        #    Prefer activated_at (set when the program is activated).
        #    Fall back to created_at for programs activated before the field existed.
        count_from = program.activated_at or program.created_at

        # 3. Count every completed workout entry (training days + rest days) since activation.
        days_completed = Workout.objects.filter(
            user=request.user,
            is_done=True,
            datetime__gte=count_from,
        ).count()

        # 4. Determine position in cycle (0-indexed), then convert to 1-indexed day_number.
        cycle_position = days_completed % program.cycle_length  # 0-indexed
        current_day_number = cycle_position + 1                 # 1-indexed

        # 5. Fetch the matching program day.
        try:
            current_day = program.days.get(day_number=current_day_number)
        except Exception:
            # Shouldn't happen if data is consistent, but be safe.
            return Response(
                {'error': 'DAY_NOT_FOUND', 'message': f'Day {current_day_number} not found in program.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            'program_id': program.id,
            'program_name': program.name,
            'cycle_length': program.cycle_length,
            'activated_at': count_from.isoformat() if count_from else None,
            'days_completed_since_activation': days_completed,
            'current_day_number': current_day_number,
            'current_day': WorkoutProgramDaySerializer(current_day).data,
        })

