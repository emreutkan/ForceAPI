from rest_framework import serializers
from .models import Workout, WorkoutExercise, ExerciseSet, TemplateWorkout, TemplateWorkoutExercise, TrainingResearch, MuscleRecovery, WorkoutMuscleRecovery, CNSRecovery, WorkoutProgram, WorkoutProgramDay, WorkoutProgramExercise
from django.utils import timezone
from datetime import datetime
from exercise.serializers import ExerciseSerializer
from exercise.models import Exercise

class CreateWorkoutSerializer(serializers.ModelSerializer):
    workout_date = serializers.DateTimeField(required=False, write_only=True)  # Accept datetime
    date = serializers.DateTimeField(required=False, write_only=True)  # Also accept 'date' for compatibility
    title = serializers.CharField(required=False)  # Make title optional
    
    class Meta:
        model = Workout
        fields = ['id', 'title', 'workout_date', 'date', 'is_done', 'is_rest_day']
        read_only_fields = ['id']
    
    def validate(self, data):
        # If it's a rest day, ignore title and is_done from request
        if data.get('is_rest_day', False):
            # Remove title and is_done if provided (we'll set them automatically)
            data.pop('title', None)
            data.pop('is_done', None)
        return data

    def create(self, validated_data):
        user = self.context['request'].user
        is_rest_day = validated_data.get('is_rest_day', False)
        
        # Accept either 'workout_date' or 'date'
        workout_datetime = validated_data.pop('workout_date', None) or validated_data.pop('date', None)
        
        # Get workout datetime (provided or default to now, which will match created_at)
        if workout_datetime:
            # If it's a naive datetime, make it timezone-aware
            if timezone.is_naive(workout_datetime):
                workout_datetime = timezone.make_aware(workout_datetime)
            # Set the datetime field
            validated_data['datetime'] = workout_datetime
            workout_date = workout_datetime.date()
        else:
            # If not provided, use current time (will be same as created_at)
            current_time = timezone.now()
            validated_data['datetime'] = current_time
            workout_date = current_time.date()
        
        # Handle title logic
        if is_rest_day:
            # Rest days always have title "Rest Day"
            validated_data['title'] = "Rest Day"
            validated_data['is_done'] = True
        elif not validated_data.get('title'):
            # Regular workouts default to date format
            validated_data['title'] = workout_date.strftime("%B, %d")
        
        # Create workout
        workout = Workout.objects.create(
            user=user,
            **validated_data
        )
        return workout

class CompleteWorkoutSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(read_only=True) # Add created_at explicitly

    class Meta:
        model = Workout
        # Expose created_at so frontend knows the date
        fields = ['id', 'title', 'notes', 'created_at', 'duration', 'intensity', 'is_done']
        
        # Restrict what can be EDITED
        read_only_fields = ['id', 'user', 'created_at', 'duration', 'intensity', 'is_done']
        
    def update(self, instance, validated_data):
        # 1. Mark as done
        validated_data['is_done'] = True
        
        # 2. Calculate Duration (If you want to do this, we need a logic. 
        # Calculate Duration using created_at
        # timezone.now() is the "Finish Time"
        # instance.created_at is the "Start Time"
        time_diff = timezone.now() - instance.created_at
        
        # Duration is stored in SECONDS (as per model definition)
        # Cap duration at 6 hours (21600 seconds) to prevent unrealistic values
        duration_seconds = int(time_diff.total_seconds())
        validated_data['duration'] = min(duration_seconds, 21600)  # Max 6 hours 
        
        # 3. Calculate Intensity (Placeholder logic)
        # instance.intensity = calculate_intensity(instance)
        
        return super().update(instance, validated_data)

def calculate_set_insights(exercise_set, exercise, workout_exercise=None):
    """
    Calculate insights for a set based on exercise type, reps, and TUT.
    Returns dict with 'good' and 'bad' insights.
    """
    insights = {'good': {}, 'bad': {}}
    
    # Skip insights for warmup sets
    if exercise_set.is_warmup:
        return insights
    
    reps = exercise_set.reps if exercise_set.reps else 0
    total_tut = exercise_set.total_tut if exercise_set.total_tut else None
    is_compound = exercise.category == 'compound' if exercise else False
    
    # Compound exercise insights
    if is_compound:
        # Junk volume check: Sets 3+ on compound exercises tax CNS without much benefit
        if workout_exercise:
            # Count non-warmup sets for this exercise
            non_warmup_sets = workout_exercise.sets.filter(is_warmup=False).order_by('set_number')
            total_non_warmup_sets = non_warmup_sets.count()
            
            # Get the position of this set among non-warmup sets (1-indexed)
            set_position = list(non_warmup_sets.values_list('id', flat=True)).index(exercise_set.id) + 1
            
            # If more than 2 sets and this is set 3 or higher
            if total_non_warmup_sets > 2 and set_position > 2:
                insights['bad']['junk_volume'] = {
                    'reason': 'Junk Volume: Sets beyond the first 2 on compound exercises provide diminishing returns while significantly taxing your CNS (Central Nervous System). The first 2 sets provide the majority of the stimulus, and additional sets primarily increase fatigue and recovery time without proportional gains.',
                    'set_position': set_position,
                    'total_sets': total_non_warmup_sets,
                    'optimal_sets': '2 sets for compound exercises'
                }
        # Rep range check (6-8 is optimal for compound)
        if reps < 6 or reps > 8:
            insights['bad']['rep_range'] = {
                'reason': 'For Compound Exercises 6–8 reps is the Superior Hypertrophy Range. When you do big lifts for high reps (12+), your cardiovascular system or lower back often fatigues before the target muscle. This range taxes your CNS (Central Nervous System) and joints more than your metabolism. You won\'t feel a "burn" (metabolic stress), you will feel crushed (mechanical fatigue).',
                'current_reps': reps,
                'optimal_range': '6-8'
            }
        else:
            insights['good']['rep_range'] = {
                'reason': 'Optimal rep range for compound exercises (6-8 reps)',
                'current_reps': reps
            }
        
        # TUT analysis (if available)
        if total_tut is not None and total_tut > 0:
            # Check if TUT is in myofibrillar hypertrophy sweet spot (24-35 seconds)
            if 24 <= total_tut <= 35:
                insights['good']['tut_sweet_spot'] = {
                    'reason': 'It is the sweet spot for myofibrillar hypertrophy (increasing the density/size of contractile fibers).',
                    'current_tut': total_tut,
                    'optimal_range': '24-35 seconds'
                }
            
            # Check TUT relative to rep count
            min_tut = reps * 3  # Minimum: 3 seconds per rep
            max_tut = reps * 4.5  # Maximum: 4.5 seconds per rep
            
            if total_tut < min_tut:
                insights['bad']['tut_too_fast'] = {
                    'reason': f'Too Fast: If you did {reps} reps in {total_tut} seconds ({total_tut/reps:.1f}s per rep), you are likely using momentum (bouncing the weight) or cutting the eccentric too short. You miss growth signals.',
                    'current_tut': total_tut,
                    'optimal_range': f'{min_tut}-{max_tut} seconds',
                    'seconds_per_rep': round(total_tut / reps, 1) if reps > 0 else 0
                }
            elif total_tut > max_tut:
                insights['bad']['tut_too_slow'] = {
                    'reason': f'Drifting into Fatigue: If {reps} reps take {total_tut} seconds, you are likely pausing too long at the top/bottom (resting) or moving impressively slow but with sub-maximal loads.',
                    'current_tut': total_tut,
                    'optimal_range': f'{min_tut}-{max_tut} seconds',
                    'seconds_per_rep': round(total_tut / reps, 1) if reps > 0 else 0
                }
            else:
                insights['good']['tut_optimal'] = {
                    'reason': f'You control the weight down (safety + growth), then fire it up (strength + fiber recruitment). This is the "Powerbuilding" standard.',
                    'current_tut': total_tut,
                    'optimal_range': f'{min_tut}-{max_tut} seconds',
                    'seconds_per_rep': round(total_tut / reps, 1) if reps > 0 else 0
                }
    
    return insights

class ExerciseSetSerializer(serializers.ModelSerializer):
    reps = serializers.IntegerField(min_value=0, max_value=100)
    reps_in_reserve = serializers.IntegerField(min_value=0, max_value=100)
    rest_time_before_set = serializers.IntegerField(min_value=0, max_value=10800)  # Max 3 hours (10800 seconds)
    total_tut = serializers.IntegerField(min_value=0, max_value=600, required=False, allow_null=True)  # Max 10 minutes (600 seconds)
    eccentric_time = serializers.IntegerField(min_value=0, max_value=600, required=False, allow_null=True)  # Max 10 minutes (600 seconds)
    concentric_time = serializers.IntegerField(min_value=0, max_value=600, required=False, allow_null=True)  # Max 10 minutes (600 seconds)
    insights = serializers.SerializerMethodField()
    
    class Meta:
        model = ExerciseSet
        fields = ['id', 'workout_exercise', 'set_number', 'reps', 'weight', 'rest_time_before_set', 'is_warmup', 'reps_in_reserve', 'eccentric_time', 'concentric_time', 'total_tut', 'insights']
        read_only_fields = ['id']
    
    def to_representation(self, instance):
        """Format weight - return integer if .00, otherwise return decimal"""
        representation = super().to_representation(instance)
        
        # Format weight field
        if 'weight' in representation and representation['weight'] is not None:
            weight_float = float(representation['weight'])
            # If it's a whole number, return as int
            if weight_float == int(weight_float):
                representation['weight'] = int(weight_float)
            else:
                representation['weight'] = weight_float
        
        return representation
    
    def get_insights(self, obj):
        """Calculate insights for this set. Only included when include_insights=True in context."""
        if not self.context.get('include_insights', False):
            return None  # Don't include insights field in list views
        
        # Get the exercise from the workout exercise
        workout_exercise = obj.workout_exercise
        exercise = workout_exercise.exercise if workout_exercise else None
        
        insights = calculate_set_insights(obj, exercise, workout_exercise)
        # Always return dict format (even if empty) when insights are enabled
        return insights if insights else {'good': {}, 'bad': {}}

class WorkoutExerciseSerializer(serializers.ModelSerializer):
    # Accept exercise as ID when writing, return full object when reading
    exercise = serializers.PrimaryKeyRelatedField(queryset=Exercise.objects.all())
    # Add this line to fetch related sets
    sets = serializers.SerializerMethodField() 
    
    class Meta:
        model = WorkoutExercise
        fields = ['id', 'workout', 'exercise', 'order', 'sets', 'one_rep_max']
        read_only_fields = ['id', 'one_rep_max']
    
    def get_sets(self, obj):
        """Get sets with context for insights if needed"""
        include_insights = self.context.get('include_insights', False)
        sets = obj.sets.all()
        serializer = ExerciseSetSerializer(
            sets, 
            many=True, 
            context={'include_insights': include_insights}
        )
        return serializer.data
    
    def to_representation(self, instance):
        # Override to return full exercise object instead of just ID
        representation = super().to_representation(instance)
        # Replace exercise ID with full exercise object
        if instance.exercise:
            representation['exercise'] = ExerciseSerializer(instance.exercise).data
        return representation

class UpdateWorkoutSerializer(serializers.ModelSerializer):
    date = serializers.DateTimeField(required=False, write_only=True)  # Accept datetime for updating
    
    class Meta:
        model = Workout
        fields = ['id', 'title', 'date', 'duration', 'intensity', 'notes', 'is_done']
        read_only_fields = ['id']
    
    def update(self, instance, validated_data):
        # Handle datetime update if provided
        workout_datetime = validated_data.pop('date', None)
        if workout_datetime:
            # If it's a naive datetime, make it timezone-aware
            if timezone.is_naive(workout_datetime):
                workout_datetime = timezone.make_aware(workout_datetime)
            validated_data['datetime'] = workout_datetime
        
        # Update workout fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

class WorkoutMuscleRecoverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutMuscleRecovery
        fields = ['muscle_group', 'condition', 'recovery_progress', 'created_at']
        read_only_fields = ['created_at']

class GetWorkoutSerializer(serializers.ModelSerializer):
    # Add this field to fetch related exercises
    # Note: 'workoutexercise_set' is the default related name. 
    # If you want it to be called 'exercises', you can rename it in the SerializerField
    exercises = serializers.SerializerMethodField()
    total_volume = serializers.SerializerMethodField()
    primary_muscles_worked = serializers.SerializerMethodField()
    secondary_muscles_worked = serializers.SerializerMethodField()
    muscle_recovery_pre_workout = serializers.SerializerMethodField()
    cns_load = serializers.SerializerMethodField()

    class Meta:
        model = Workout
        fields = ['id', 'title', 'datetime', 'duration', 'intensity', 'notes', 'is_done', 'is_rest_day', 'calories_burned', 'created_at', 'updated_at', 'exercises', 'total_volume', 'primary_muscles_worked', 'secondary_muscles_worked', 'muscle_recovery_pre_workout', 'cns_load']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_exercises(self, obj):
        """Get exercises with context for insights if needed"""
        include_insights = self.context.get('include_insights', False)
        exercises = obj.workoutexercise_set.all()
        serializer = WorkoutExerciseSerializer(
            exercises, 
            many=True, 
            context={'include_insights': include_insights}
        )
        return serializer.data
    
    def get_total_volume(self, obj):
        """Calculate total volume (sum of weight * reps for all sets)"""
        total = 0
        # Use prefetched data instead of new query
        for workout_exercise in obj.workoutexercise_set.all():
            for exercise_set in workout_exercise.sets.all():
                total += float(exercise_set.weight) * exercise_set.reps
        return round(total, 2)
    
    def get_primary_muscles_worked(self, obj):
        """Get unique primary muscle groups from all exercises"""
        # Use prefetched data instead of new query
        primary_muscles = set()
        for workout_exercise in obj.workoutexercise_set.all():
            exercise = workout_exercise.exercise
            if exercise and exercise.primary_muscle:
                primary_muscles.add(exercise.primary_muscle)
        return sorted(list(primary_muscles))
    
    def get_secondary_muscles_worked(self, obj):
        """Get unique secondary muscle groups from all exercises"""
        # Use prefetched data instead of new query
        secondary_muscles = set()
        for workout_exercise in obj.workoutexercise_set.all():
            exercise = workout_exercise.exercise
            if exercise and exercise.secondary_muscles:
                for muscle in exercise.secondary_muscles:
                    if muscle:
                        secondary_muscles.add(muscle)
        return sorted(list(secondary_muscles))
    
    def get_muscle_recovery_pre_workout(self, obj):
        """Get pre-workout muscle recovery data for this workout"""
        pre_recovery = WorkoutMuscleRecovery.objects.filter(
            workout=obj,
            condition='pre'
        )
        if pre_recovery.exists():
            # Convert to dict format: {muscle_group: recovery_progress}
            recovery_dict = {}
            for record in pre_recovery:
                recovery_dict[record.muscle_group] = float(record.recovery_progress)
            return recovery_dict
        return {}
    
    def get_cns_load(self, obj):
        """Calculate and return CNS (Central Nervous System) load for this workout"""
        if obj.is_rest_day:
            return 0.0
        return obj.calculate_cns_load()

class TemplateWorkoutExerciseSerializer(serializers.ModelSerializer):
    exercise = ExerciseSerializer(read_only=True)
    
    class Meta:
        model = TemplateWorkoutExercise
        fields = ['id', 'exercise', 'order']
        read_only_fields = ['id']

class CreateTemplateWorkoutSerializer(serializers.ModelSerializer):
    exercises = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        help_text="List of exercise IDs"
    )
    
    class Meta:
        model = TemplateWorkout
        fields = ['id', 'title', 'exercises', 'notes']
        read_only_fields = ['id']
    
    def create(self, validated_data):
        user = self.context['request'].user
        exercise_ids = validated_data.pop('exercises', [])
        
        # Create template workout
        template_workout = TemplateWorkout.objects.create(
            user=user,
            **validated_data
        )
        
        # Add exercises with order
        for order, exercise_id in enumerate(exercise_ids, start=1):
            from exercise.models import Exercise
            try:
                exercise = Exercise.objects.get(id=exercise_id)
                TemplateWorkoutExercise.objects.create(
                    template_workout=template_workout,
                    exercise=exercise,
                    order=order
                )
            except Exercise.DoesNotExist:
                continue  # Skip invalid exercise IDs
        
        return template_workout

class GetTemplateWorkoutSerializer(serializers.ModelSerializer):
    exercises = TemplateWorkoutExerciseSerializer(source='templateworkoutexercise_set', many=True, read_only=True)
    primary_muscle_groups = serializers.SerializerMethodField()
    secondary_muscle_groups = serializers.SerializerMethodField()
    
    class Meta:
        model = TemplateWorkout
        fields = ['id', 'title', 'exercises', 'primary_muscle_groups', 'secondary_muscle_groups', 'notes', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_primary_muscle_groups(self, obj):
        """Get unique primary muscle groups from all exercises"""
        template_exercises = TemplateWorkoutExercise.objects.filter(template_workout=obj).select_related('exercise')
        primary_muscles = set()
        for template_exercise in template_exercises:
            exercise = template_exercise.exercise
            if exercise.primary_muscle:
                primary_muscles.add(exercise.primary_muscle)
        return sorted(list(primary_muscles))
    
    def get_secondary_muscle_groups(self, obj):
        """Get unique secondary muscle groups from all exercises"""
        template_exercises = TemplateWorkoutExercise.objects.filter(template_workout=obj).select_related('exercise')
        secondary_muscles = set()
        for template_exercise in template_exercises:
            exercise = template_exercise.exercise
            if exercise.secondary_muscles:
                for muscle in exercise.secondary_muscles:
                    if muscle:
                        secondary_muscles.add(muscle)
        return sorted(list(secondary_muscles))

class TrainingResearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingResearch
        fields = [
            'id', 'title', 'summary', 'content', 'category', 'tags',
            'source_title', 'source_url', 'source_authors', 'publication_date',
            'evidence_level', 'confidence_score', 'applicable_muscle_groups',
            'applicable_exercise_types', 'parameters', 'is_active', 'is_validated',
            'priority', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class MuscleRecoverySerializer(serializers.ModelSerializer):
    hours_until_recovery = serializers.SerializerMethodField()
    recovery_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = MuscleRecovery
        fields = [
            'id', 'muscle_group', 'fatigue_score', 'total_sets',
            'recovery_hours', 'recovery_until', 'is_recovered',
            'source_workout', 'hours_until_recovery', 'recovery_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_hours_until_recovery(self, obj):
        """Calculate hours remaining until recovery"""
        if obj.recovery_until and not obj.is_recovered:
            delta = obj.recovery_until - timezone.now()
            if delta.total_seconds() > 0:
                return round(delta.total_seconds() / 3600, 1)
        return 0
    
    def get_recovery_percentage(self, obj):
        """
        Calculate recovery percentage using non-linear J-curve model.
        Recovery is NOT linear - follows inflammation → protein synthesis → structural repair phases.
        """
        if not obj.recovery_until or obj.is_recovered:
            return 100
        
        # Calculate percentage based on time elapsed
        workout_time = obj.source_workout.datetime if obj.source_workout else obj.created_at
        total_duration = obj.recovery_until - workout_time
        elapsed = timezone.now() - workout_time
        
        if total_duration.total_seconds() <= 0:
            return 100
        
        # Non-linear recovery curve (J-curve model)
        # 0-24h: Inflammation phase - slower recovery (0-30%)
        # 24-48h: Protein synthesis phase - accelerated recovery (30-70%)
        # 48h+: Structural repair - final recovery (70-100%)
        linear_progress = elapsed.total_seconds() / total_duration.total_seconds()
        
        # Apply J-curve transformation
        if linear_progress <= 0.3:
            # Early phase - inflammation, slower recovery
            non_linear_progress = linear_progress * 0.7
        elif linear_progress <= 0.7:
            # Mid phase - protein synthesis, accelerated recovery
            non_linear_progress = 0.21 + (linear_progress - 0.3) * 1.225
        else:
            # Final phase - structural repair completion
            non_linear_progress = 0.7 + (linear_progress - 0.7) * 1.0
        
        percentage = non_linear_progress * 100
        return min(100, max(0, round(percentage, 1)))

class CNSRecoverySerializer(serializers.ModelSerializer):
    hours_until_recovery = serializers.SerializerMethodField()
    recovery_percentage = serializers.SerializerMethodField()

    class Meta:
        model = CNSRecovery
        fields = [
            'id', 'cns_load', 'recovery_hours', 'recovery_until',
            'is_recovered', 'source_workout', 'hours_until_recovery',
            'recovery_percentage', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_hours_until_recovery(self, obj):
        """Calculate hours until recovery"""
        if obj.recovery_until:
            delta = obj.recovery_until - timezone.now()
            if delta.total_seconds() > 0:
                return round(delta.total_seconds() / 3600, 1)
        return 0

    def get_recovery_percentage(self, obj):
        """
        Calculate CNS recovery percentage using non-linear J-curve model.
        Same model as muscle recovery - follows inflammation → protein synthesis → structural repair phases.
        """
        if not obj.recovery_until or obj.is_recovered:
            return 100

        # Calculate percentage based on time elapsed
        workout_time = obj.source_workout.datetime if obj.source_workout else obj.created_at
        total_duration = obj.recovery_until - workout_time
        elapsed = timezone.now() - workout_time

        if total_duration.total_seconds() <= 0:
            return 100

        # Non-linear recovery curve (J-curve model)
        # 0-24h: Inflammation phase - slower recovery (0-30%)
        # 24-48h: Protein synthesis phase - accelerated recovery (30-70%)
        # 48h+: Structural repair - final recovery (70-100%)
        linear_progress = elapsed.total_seconds() / total_duration.total_seconds()

        # Apply J-curve transformation
        if linear_progress <= 0.3:
            # Early phase - inflammation, slower recovery
            non_linear_progress = linear_progress * 0.7
        elif linear_progress <= 0.7:
            # Mid phase - protein synthesis, accelerated recovery
            non_linear_progress = 0.21 + (linear_progress - 0.3) * 1.225
        else:
            # Final phase - structural repair completion
            non_linear_progress = 0.7 + (linear_progress - 0.7) * 1.0

        percentage = non_linear_progress * 100
        return min(100, max(0, round(percentage, 1)))


# ---------------------------------------------------------------------------
# Workout Program serializers
# ---------------------------------------------------------------------------

class WorkoutProgramExerciseInputSerializer(serializers.Serializer):
    """Used when creating a program day's exercises."""
    exercise_id = serializers.IntegerField()
    target_sets = serializers.IntegerField(min_value=1, max_value=50)
    order = serializers.IntegerField(min_value=1, required=False)


class WorkoutProgramDayInputSerializer(serializers.Serializer):
    """Used when creating a program's days."""
    day_number = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255)
    is_rest_day = serializers.BooleanField(default=False)
    exercises = WorkoutProgramExerciseInputSerializer(many=True, required=False, default=list)

    def validate(self, data):
        if data.get('is_rest_day') and data.get('exercises'):
            raise serializers.ValidationError("Rest days cannot have exercises.")
        return data


class CreateWorkoutProgramSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    cycle_length = serializers.IntegerField(min_value=1, max_value=30)
    days = WorkoutProgramDayInputSerializer(many=True)

    def validate(self, data):
        cycle_length = data['cycle_length']
        days = data['days']

        if len(days) != cycle_length:
            raise serializers.ValidationError(
                f"cycle_length is {cycle_length} but {len(days)} day(s) were provided. "
                "The number of days must match cycle_length."
            )

        day_numbers = [d['day_number'] for d in days]
        if sorted(day_numbers) != list(range(1, cycle_length + 1)):
            raise serializers.ValidationError(
                f"day_number values must be exactly 1 through {cycle_length}, each used once."
            )

        return data

    def create(self, validated_data):
        from exercise.models import Exercise as ExerciseModel
        user = self.context['request'].user
        days_data = validated_data.pop('days')

        program = WorkoutProgram.objects.create(user=user, **validated_data)

        for day_data in days_data:
            exercises_data = day_data.pop('exercises', [])
            day = WorkoutProgramDay.objects.create(program=program, **day_data)

            for idx, ex_data in enumerate(exercises_data, start=1):
                exercise_id = ex_data['exercise_id']
                try:
                    exercise = ExerciseModel.objects.get(id=exercise_id)
                except ExerciseModel.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Exercise with id {exercise_id} does not exist."
                    )
                WorkoutProgramExercise.objects.create(
                    program_day=day,
                    exercise=exercise,
                    order=ex_data.get('order', idx),
                    target_sets=ex_data['target_sets'],
                )

        return program


class WorkoutProgramExerciseSerializer(serializers.ModelSerializer):
    exercise = ExerciseSerializer(read_only=True)

    class Meta:
        model = WorkoutProgramExercise
        fields = ['id', 'exercise', 'order', 'target_sets']
        read_only_fields = ['id']


class WorkoutProgramDaySerializer(serializers.ModelSerializer):
    exercises = WorkoutProgramExerciseSerializer(many=True, read_only=True)

    class Meta:
        model = WorkoutProgramDay
        fields = ['id', 'day_number', 'name', 'is_rest_day', 'exercises']
        read_only_fields = ['id']


class WorkoutProgramSerializer(serializers.ModelSerializer):
    days = WorkoutProgramDaySerializer(many=True, read_only=True)

    class Meta:
        model = WorkoutProgram
        fields = ['id', 'name', 'cycle_length', 'is_active', 'days', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class UpdateWorkoutProgramSerializer(serializers.ModelSerializer):
    """For renaming a program."""
    class Meta:
        model = WorkoutProgram
        fields = ['name']