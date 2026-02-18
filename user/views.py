from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from .serializers import UserSerializer
from .models import UserProfile, WeightHistory
from rest_framework.pagination import PageNumberPagination
from body_measurements.models import BodyMeasurement
import csv
import io
import zipfile
import json
from django.http import HttpResponse
from django.conf import settings
import logging
from django.db import transaction
from django.db.models import Max
from core.mixins import ConditionalGetMixin
from workout.models import Workout, WorkoutExercise, ExerciseSet, TemplateWorkout, TemplateWorkoutExercise
from exercise.models import Exercise
from .models import Preferences
from datetime import date

User = get_user_model()


class UserProfileView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_last_modified(self, request, **kwargs):
        return getattr(request.user, "updated_at", None)

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateHeightView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        height = request.data.get('height')

        if height is None:
            return Response({'error': 'height field is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            height = float(height)
            if height <= 0:
                return Response({'error': 'height must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({'error': 'height must be a valid number'}, status=status.HTTP_400_BAD_REQUEST)

        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.height = height
        profile.save()

        return Response({'height': str(profile.height), 'message': 'Height updated successfully'}, status=status.HTTP_200_OK)


class UpdateGenderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        gender = request.data.get('gender')

        if gender is None:
            return Response({'error': 'gender field is required'}, status=status.HTTP_400_BAD_REQUEST)

        if gender not in ['male', 'female']:
            return Response({'error': 'gender must be either "male" or "female"'}, status=status.HTTP_400_BAD_REQUEST)

        request.user.gender = gender
        request.user.save()

        return Response({'gender': request.user.gender, 'message': 'Gender updated successfully'}, status=status.HTTP_200_OK)


class UpdateWeightView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        weight = request.data.get('weight')

        if weight is None:
            return Response({'error': 'weight field is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            weight = float(weight)
            if weight <= 0:
                return Response({'error': 'weight must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({'error': 'weight must be a valid number'}, status=status.HTTP_400_BAD_REQUEST)

        weight_entry = WeightHistory.objects.create(user=request.user, weight=weight)

        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.body_weight = weight
        profile.save()

        return Response({
            'weight': str(weight_entry.weight),
            'date': weight_entry.created_at.isoformat(),
            'message': 'Weight updated successfully'
        }, status=status.HTTP_200_OK)


class WeightHistoryPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 100


class GetWeightHistoryView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = WeightHistoryPagination

    def get_last_modified(self, request, **kwargs):
        return WeightHistory.objects.filter(user=request.user).aggregate(Max("updated_at"))["updated_at__max"]

    def get(self, request):
        paginator = WeightHistoryPagination()
        weight_history = WeightHistory.objects.filter(user=request.user).order_by('-created_at')
        page = paginator.paginate_queryset(weight_history, request)

        results = []
        for entry in page:
            entry_date = entry.created_at.date()
            body_fat = None
            body_measurement = BodyMeasurement.objects.filter(
                user=request.user,
                created_at__date=entry_date
            ).first()
            if body_measurement and body_measurement.body_fat_percentage:
                body_fat = float(body_measurement.body_fat_percentage)
            results.append({
                'id': entry.id,
                'date': entry.created_at.isoformat(),
                'weight': float(entry.weight),
                'bodyfat': body_fat
            })

        return paginator.get_paginated_response(results)


class DeleteWeightView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, weight_id):
        try:
            weight_entry = WeightHistory.objects.get(id=weight_id, user=request.user)
        except WeightHistory.DoesNotExist:
            return Response({'error': 'Weight entry not found'}, status=status.HTTP_404_NOT_FOUND)

        entry_date = weight_entry.created_at.date()
        delete_bodyfat = request.query_params.get('delete_bodyfat', 'false').lower() == 'true'

        deleted_bodyfat = False
        if delete_bodyfat:
            body_measurements = BodyMeasurement.objects.filter(user=request.user, created_at__date=entry_date)
            if body_measurements.exists():
                body_measurements.delete()
                deleted_bodyfat = True

        weight_entry.delete()

        latest_weight = WeightHistory.objects.filter(user=request.user).order_by('-created_at').first()
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.body_weight = latest_weight.weight if latest_weight else None
        profile.save()

        response_data = {'message': 'Weight entry deleted successfully', 'deleted_date': entry_date.isoformat()}
        if delete_bodyfat:
            response_data['bodyfat_deleted'] = deleted_bodyfat

        return Response(response_data, status=status.HTTP_200_OK)


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        with transaction.atomic():
            request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DataExportView(ConditionalGetMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        export_format = request.query_params.get('format', 'json').lower()
        user = request.user

        data = {
            'profile': {
                'gender': user.gender,
                'height': float(user.userprofile.height) if user.userprofile.height else None,
                'weight': float(user.userprofile.body_weight) if user.userprofile.body_weight else None,
            },
            'preferences': {
                'auto_warmup_set': user.preferences.auto_warmup_set,
                'rest_time': user.preferences.rest_time,
                'units': user.preferences.units,
            },
            'weight_history': list(WeightHistory.objects.filter(user=user).values('weight', 'created_at')),
            'body_measurements': list(BodyMeasurement.objects.filter(user=user).values(
                'weight', 'body_fat_percentage', 'neck', 'waist', 'hip', 'created_at'
            )),
            'workouts': [],
            'template_workouts': [],
        }

        for entry in data['weight_history']:
            entry['created_at'] = entry['created_at'].isoformat()
            entry['weight'] = float(entry['weight'])

        for entry in data['body_measurements']:
            entry['created_at'] = entry['created_at'].isoformat()
            for key in ['weight', 'body_fat_percentage', 'neck', 'waist', 'hip']:
                if entry[key]:
                    entry[key] = float(entry[key])

        workouts = Workout.objects.filter(user=user).prefetch_related('workoutexercise_set__exercise', 'workoutexercise_set__sets')
        for w in workouts:
            w_data = {
                'title': w.title,
                'datetime': w.datetime.isoformat(),
                'duration': w.duration,
                'intensity': w.intensity,
                'notes': w.notes,
                'is_done': w.is_done,
                'is_rest_day': w.is_rest_day,
                'calories_burned': float(w.calories_burned) if w.calories_burned else None,
                'exercises': []
            }
            for we in w.workoutexercise_set.all():
                we_data = {
                    'exercise_name': we.exercise.name,
                    'order': we.order,
                    'sets': list(we.sets.values('set_number', 'reps', 'weight', 'rest_time_before_set', 'is_warmup', 'reps_in_reserve', 'eccentric_time', 'concentric_time', 'total_tut'))
                }
                for s in we_data['sets']:
                    s['weight'] = float(s['weight'])
                w_data['exercises'].append(we_data)
            data['workouts'].append(w_data)

        templates = TemplateWorkout.objects.filter(user=user).prefetch_related('templateworkoutexercise_set__exercise')
        for t in templates:
            t_data = {
                'title': t.title,
                'notes': t.notes,
                'exercises': [
                    {'exercise_name': twe.exercise.name, 'order': twe.order}
                    for twe in t.templateworkoutexercise_set.all()
                ]
            }
            data['template_workouts'].append(t_data)

        if export_format == 'csv':
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as zip_file:
                weight_io = io.StringIO()
                weight_writer = csv.writer(weight_io)
                weight_writer.writerow(['Date', 'Weight (kg)'])
                for entry in data['weight_history']:
                    weight_writer.writerow([entry['created_at'], entry['weight']])
                zip_file.writestr('weight_history.csv', weight_io.getvalue())

                workout_io = io.StringIO()
                workout_writer = csv.writer(workout_io)
                workout_writer.writerow(['Date', 'Workout Title', 'Exercise', 'Set #', 'Weight', 'Reps', 'Is Warmup', 'RIR'])
                for w in data['workouts']:
                    for we in w['exercises']:
                        for s in we['sets']:
                            workout_writer.writerow([
                                w['datetime'], w['title'], we['exercise_name'],
                                s['set_number'], s['weight'], s['reps'],
                                s['is_warmup'], s['reps_in_reserve']
                            ])
                zip_file.writestr('workouts.csv', workout_io.getvalue())

                bm_io = io.StringIO()
                bm_writer = csv.writer(bm_io)
                bm_writer.writerow(['Date', 'Weight', 'Body Fat %', 'Neck', 'Waist', 'Hip'])
                for bm in data['body_measurements']:
                    bm_writer.writerow([
                        bm['created_at'], bm['weight'], bm['body_fat_percentage'],
                        bm['neck'], bm['waist'], bm['hip']
                    ])
                zip_file.writestr('body_measurements.csv', bm_io.getvalue())

            buffer.seek(0)
            response = HttpResponse(buffer, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="force_data_export_{user.email}_{date.today()}.zip"'
            return response

        else:
            response_json = json.dumps(data, indent=4)
            response = HttpResponse(response_json, content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="force_data_export_{user.email}_{date.today()}.json"'
            return response


class DataImportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if 'file' not in request.FILES:
            return Response({'error': 'No file uploaded'}, status=status.HTTP_400_BAD_REQUEST)

        import_file = request.FILES['file']
        try:
            data = json.load(import_file)
        except json.JSONDecodeError:
            return Response({'error': 'Invalid JSON file'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        with transaction.atomic():
            if 'profile' in data:
                p = data['profile']
                if 'gender' in p:
                    user.gender = p['gender']
                user.save()
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if 'height' in p:
                    profile.height = p['height']
                if 'weight' in p:
                    profile.body_weight = p['weight']
                profile.save()

            if 'preferences' in data:
                pref = data['preferences']
                p_obj, _ = Preferences.objects.get_or_create(user=user)
                if 'auto_warmup_set' in pref:
                    p_obj.auto_warmup_set = pref['auto_warmup_set']
                if 'rest_time' in pref:
                    p_obj.rest_time = pref['rest_time']
                if 'units' in pref:
                    p_obj.units = pref['units']
                p_obj.save()

            if 'weight_history' in data:
                for entry in data['weight_history']:
                    WeightHistory.objects.get_or_create(
                        user=user,
                        weight=entry['weight'],
                        created_at=entry['created_at']
                    )

            if 'body_measurements' in data:
                for bm in data['body_measurements']:
                    BodyMeasurement.objects.get_or_create(
                        user=user,
                        created_at=bm['created_at'],
                        defaults={
                            'weight': bm.get('weight'),
                            'body_fat_percentage': bm.get('body_fat_percentage'),
                            'neck': bm.get('neck'),
                            'waist': bm.get('waist'),
                            'hip': bm.get('hip')
                        }
                    )

            if 'workouts' in data:
                for w in data['workouts']:
                    workout, created = Workout.objects.get_or_create(
                        user=user,
                        datetime=w['datetime'],
                        defaults={
                            'title': w['title'],
                            'duration': w['duration'],
                            'intensity': w['intensity'],
                            'notes': w.get('notes'),
                            'is_done': w.get('is_done', True),
                            'is_rest_day': w.get('is_rest_day', False),
                            'calories_burned': w.get('calories_burned')
                        }
                    )
                    if created:
                        for ex in w.get('exercises', []):
                            exercise = Exercise.objects.filter(name__iexact=ex['exercise_name']).first()
                            if exercise:
                                we = WorkoutExercise.objects.create(
                                    workout=workout,
                                    exercise=exercise,
                                    order=ex['order']
                                )
                                for s in ex.get('sets', []):
                                    ExerciseSet.objects.create(
                                        workout_exercise=we,
                                        set_number=s['set_number'],
                                        reps=s['reps'],
                                        weight=s['weight'],
                                        rest_time_before_set=s.get('rest_time_before_set', 0),
                                        is_warmup=s.get('is_warmup', False),
                                        reps_in_reserve=s.get('reps_in_reserve', 0),
                                        eccentric_time=s.get('eccentric_time'),
                                        concentric_time=s.get('concentric_time'),
                                        total_tut=s.get('total_tut')
                                    )

            if 'template_workouts' in data:
                for t in data['template_workouts']:
                    template, created = TemplateWorkout.objects.get_or_create(
                        user=user,
                        title=t['title'],
                        defaults={'notes': t.get('notes')}
                    )
                    if created:
                        for ex in t.get('exercises', []):
                            exercise = Exercise.objects.filter(name__iexact=ex['exercise_name']).first()
                            if exercise:
                                TemplateWorkoutExercise.objects.create(
                                    template_workout=template,
                                    exercise=exercise,
                                    order=ex['order']
                                )

        return Response({'message': 'Data imported successfully'}, status=status.HTTP_201_CREATED)
