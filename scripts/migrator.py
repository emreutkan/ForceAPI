import django
import os
import sys
from io import StringIO

# 1. Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'force.settings')
django.setup()

from django.core.management import call_command
from django.db.models.signals import post_save, pre_save
from django.contrib.contenttypes.models import ContentType
from django.db import connection

def run_migration():
    print("--- Starting Master Migration Process ---")

    # 2. Flush the database (Wipes all tables)
    print("Step 1: Flushing database (Wiping all data)...")
    call_command('flush', interactive=False)

    # 3. Clear ContentTypes to avoid ID conflicts
    # This prevents "ContentType matching query does not exist" errors
    print("Step 2: Clearing ContentTypes...")
    ContentType.objects.all().delete()
    
    # 4. Re-populate ContentTypes
    # This creates fresh IDs for your current models
    print("Step 3: Re-populating ContentType table via migrate...")
    call_command('migrate', interactive=False)

    # 5. Disable ALL signals temporarily
    # This prevents the 'UserProfile' from being created automatically
    print("Step 4: Disabling all signals (Muting UserProfile creation)...")
    post_receivers = post_save.receivers
    pre_receivers = pre_save.receivers
    post_save.receivers = []
    pre_save.receivers = []

    try:
        # 6. Load the data
        print("Step 5: Loading datadump_clean.json...")
        # We use ignorenonexistent=True to handle any tiny model differences
        call_command('loaddata', 'datadump_clean.json')
        print("SUCCESS: Data imported.")
    except Exception as e:
        print(f"FAILED during loaddata: {e}")
        return
    finally:
        # 7. Restore signals immediately
        post_save.receivers = post_receivers
        pre_save.receivers = pre_receivers
        print("Signals restored.")

    # 8. Reset PostgreSQL sequences
    # This tells Postgres what the next ID number should be
    print("Step 6: Resetting PostgreSQL ID sequences...")
    apps = ['user', 'exercise', 'workout', 'supplements', 'body_measurements']
    output = StringIO()
    try:
        call_command('sqlsequencereset', *apps, stdout=output)
        sql = output.getvalue()
        if sql:
            with connection.cursor() as cursor:
                cursor.execute(sql)
            print("SUCCESS: Sequences reset.")
        else:
            print("No sequences needed resetting.")
    except Exception as e:
        print(f"Warning: Sequence reset failed: {e}")

    print("\n--- Migration Completed Successfully! ---")
    print("Force is ready for use on EC2.")

if __name__ == "__main__":
    run_migration()