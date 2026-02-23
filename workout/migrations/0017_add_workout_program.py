from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('exercise', '0002_alter_exercise_image'),
        ('user', '0011_customuser_supabase_uid'),
        ('workout', '0016_fix_workoutmusclerecovery_sequence'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkoutProgram',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=255)),
                ('cycle_length', models.PositiveIntegerField()),
                ('is_active', models.BooleanField(default=False)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='workout_programs', to='user.customuser')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WorkoutProgramDay',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('day_number', models.PositiveIntegerField()),
                ('name', models.CharField(max_length=255)),
                ('is_rest_day', models.BooleanField(default=False)),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='days', to='workout.workoutprogram')),
            ],
            options={
                'ordering': ['day_number'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='workoutprogramday',
            unique_together={('program', 'day_number')},
        ),
        migrations.CreateModel(
            name='WorkoutProgramExercise',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('target_sets', models.PositiveIntegerField(default=3)),
                ('exercise', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='exercise.exercise')),
                ('program_day', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exercises', to='workout.workoutprogramday')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
    ]
