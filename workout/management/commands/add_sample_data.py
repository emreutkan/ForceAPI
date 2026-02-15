from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import random

from user.models import CustomUser, UserProfile, WeightHistory
from exercise.models import Exercise
from workout.models import Workout, WorkoutExercise, ExerciseSet
from body_measurements.models import BodyMeasurement


class Command(BaseCommand):
    help = 'Adds sample data for a specific user (irfanemreutkan@outlook.com)'

    def handle(self, *args, **options):
        email = 'irfanemreutkan@outlook.com'
        
        # Get or create user
        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                'first_name': 'Irfan',
                'last_name': 'Utkan',
                'is_verified': True,
                'gender': 'male',
            }
        )
        
        if created:
            user.set_password('sample123')  # Set a default password
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created user: {email}'))
        else:
            self.stdout.write(self.style.WARNING(f'User already exists: {email}'))
        
        # Update user profile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.body_weight = Decimal('75.5')
        profile.height = Decimal('175.0')
        profile.save()
        self.stdout.write(self.style.SUCCESS('Updated user profile'))
        
        # Add weight history (last 3 months)
        self.stdout.write('Adding weight history...')
        # Delete existing weight history for this user to avoid duplicates
        WeightHistory.objects.filter(user=user).delete()
        
        today = timezone.now().date()
        for i in range(12):  # 12 weeks
            weight_date = today - timedelta(weeks=i)
            weight = Decimal('75.5') - Decimal(str(i * 0.2))  # Gradual weight loss
            measurement_datetime = timezone.make_aware(timezone.datetime.combine(weight_date, timezone.datetime.min.time()))
            WeightHistory.objects.create(
                user=user,
                weight=weight,
                created_at=measurement_datetime
            )
        self.stdout.write(self.style.SUCCESS(f'Added {12} weight history entries'))
        
        # Add body measurements
        self.stdout.write('Adding body measurements...')
        # Delete existing body measurements for this user to avoid duplicates
        BodyMeasurement.objects.filter(user=user).delete()
        
        for i in range(3):  # 3 measurements over time
            measurement_date_only = today - timedelta(weeks=i*4)
            measurement_date = timezone.make_aware(timezone.datetime.combine(measurement_date_only, timezone.datetime.min.time()))
            BodyMeasurement.objects.create(
                user=user,
                height=Decimal('175.0'),
                weight=Decimal('75.5') - Decimal(str(i * 0.8)),
                waist=Decimal('85.0') - Decimal(str(i * 1.5)),
                neck=Decimal('38.0'),
                gender='male',
                created_at=measurement_date,
            )
        self.stdout.write(self.style.SUCCESS('Added body measurements'))
        
        # Get some common exercises
        exercises = Exercise.objects.filter(is_active=True)[:15]
        if not exercises.exists():
            self.stdout.write(self.style.ERROR('No exercises found in database. Please populate exercises first.'))
            return
        
        exercise_list = list(exercises)
        
        # Common workout patterns
        workout_templates = [
            {
                'title': 'Push Day',
                'exercises': ['Bench Press', 'Overhead Press', 'Tricep Extension', 'Lateral Raise'],
                'intensity': 'high'
            },
            {
                'title': 'Pull Day',
                'exercises': ['Barbell Row', 'Pull-up', 'Bicep Curl', 'Face Pull'],
                'intensity': 'high'
            },
            {
                'title': 'Leg Day',
                'exercises': ['Squat', 'Romanian Deadlift', 'Leg Press', 'Leg Curl'],
                'intensity': 'high'
            },
            {
                'title': 'Upper Body',
                'exercises': ['Bench Press', 'Barbell Row', 'Overhead Press', 'Bicep Curl'],
                'intensity': 'medium'
            },
            {
                'title': 'Full Body',
                'exercises': ['Squat', 'Bench Press', 'Barbell Row', 'Overhead Press'],
                'intensity': 'medium'
            },
        ]
        
        # Create workouts for the last 8 weeks (3-4 workouts per week)
        self.stdout.write('Creating workouts...')
        workout_count = 0
        today_datetime = timezone.now()
        
        # Create workouts over the past 8 weeks
        for week in range(8):
            # 3-4 workouts per week
            workouts_per_week = random.randint(3, 4)
            for day in range(workouts_per_week):
                # Spread workouts throughout the week
                days_ago = (week * 7) + (day * 2) + random.randint(0, 1)
                workout_date = today_datetime - timedelta(days=days_ago)
                
                # Select a workout template
                template = random.choice(workout_templates)
                
                # Create workout
                workout = Workout.objects.create(
                    user=user,
                    title=template['title'],
                    datetime=workout_date,
                    duration=random.randint(3600, 7200),  # 1-2 hours
                    intensity=template['intensity'],
                    is_done=True,
                    notes=f'Sample workout - {template["title"]}'
                )
                
                # Add exercises to workout
                exercise_order = 0
                for exercise_name in template['exercises']:
                    # Find matching exercise (case-insensitive partial match)
                    exercise = None
                    for ex in exercise_list:
                        if exercise_name.lower() in ex.name.lower() or ex.name.lower() in exercise_name.lower():
                            exercise = ex
                            break
                    
                    if not exercise:
                        # If not found, use a random exercise
                        exercise = random.choice(exercise_list)
                    
                    # Create workout exercise
                    workout_exercise = WorkoutExercise.objects.create(
                        workout=workout,
                        exercise=exercise,
                        order=exercise_order
                    )
                    exercise_order += 1
                    
                    # Add sets (3-5 sets per exercise)
                    num_sets = random.randint(3, 5)
                    base_weight = Decimal(str(random.randint(40, 120)))
                    
                    for set_num in range(1, num_sets + 1):
                        # Progressive weight increase
                        weight = base_weight + Decimal(str((set_num - 1) * 2.5))
                        reps = random.randint(6, 12)
                        rir = random.randint(0, 3)  # Reps in reserve
                        
                        ExerciseSet.objects.create(
                            workout_exercise=workout_exercise,
                            set_number=set_num,
                            reps=reps,
                            weight=weight,
                            rest_time_before_set=random.randint(60, 180) if set_num > 1 else 0,
                            is_warmup=(set_num == 1 and random.random() < 0.3),  # 30% chance first set is warmup
                            reps_in_reserve=rir
                        )
                
                # Calculate calories and recovery
                workout.calculate_calories()
                workout.calculate_muscle_recovery()
                workout.calculate_cns_recovery()
                
                workout_count += 1
                
                if workout_count % 10 == 0:
                    self.stdout.write(f'  Created {workout_count} workouts...')
        
        self.stdout.write(self.style.SUCCESS(f'Created {workout_count} workouts'))
        
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully added sample data for {email}'))
        self.stdout.write(f'   - {workout_count} workouts')
        self.stdout.write(f'   - {12} weight history entries')
        self.stdout.write(f'   - {3} body measurements')
