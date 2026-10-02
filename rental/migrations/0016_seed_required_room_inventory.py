from django.db import migrations


# Keep the already-recorded migration node without seeding records on new databases.
class Migration(migrations.Migration):
    dependencies = [
        ('rental', '0015_guest_aadhar_back_guest_aadhar_front'),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
