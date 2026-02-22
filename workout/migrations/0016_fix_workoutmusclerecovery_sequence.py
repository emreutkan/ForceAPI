# Fix PostgreSQL sequence for WorkoutMuscleRecovery.id after restore/import.
# When data is loaded with explicit IDs, the sequence can stay at 1 and cause
# "duplicate key value violates unique constraint ... Key (id)=(1) already exists."

from django.db import migrations


def reset_workoutmusclerecovery_sequence(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT MAX(id) FROM workout_workoutmusclerecovery")
        row = cursor.fetchone()
        if row and row[0] is not None:
            cursor.execute(f"SELECT setval(pg_get_serial_sequence('workout_workoutmusclerecovery', 'id'), {row[0]})")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('workout', '0015_cnsrecovery'),
    ]

    operations = [
        migrations.RunPython(reset_workoutmusclerecovery_sequence, noop),
    ]
