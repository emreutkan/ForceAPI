Backend operations use Django management commands (manage.py). Run from project root.

  python manage.py backup_db              # SQL backup (or --json for dumpdata)
  python manage.py load_production_dump  # Load datadump_clean.json (flush + loaddata + sequences)
  python manage.py populate_exercises    # Load exercises from exercise_list.json
  python manage.py download_exercise_images   # Download images from free-exercise-db
  python manage.py generate_exercise_placeholders  # Generate placeholder images (needs Pillow)
  python manage.py add_app_store_test_user   # Create TestFlight/App Review test user

This folder may still contain shell scripts (e.g. backup_database.sh, restore_database.sh) for deployment.
