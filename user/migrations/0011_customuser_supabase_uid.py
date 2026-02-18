from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0010_set_developer_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='supabase_uid',
            field=models.UUIDField(blank=True, help_text='Supabase user UUID (sub claim in JWT)', null=True, unique=True),
        ),
    ]
