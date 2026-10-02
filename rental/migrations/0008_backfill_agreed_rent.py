"""Backfill agreed_rent from price for existing rooms

This migration sets `agreed_rent = price` for rows where `agreed_rent` is NULL/empty.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Room = apps.get_model('rental', 'Room')
    # Only update rows where agreed_rent is null
    rooms = Room.objects.filter(agreed_rent__isnull=True)
    for r in rooms:
        r.agreed_rent = r.price
        r.save(update_fields=['agreed_rent'])


def backwards(apps, schema_editor):
    Room = apps.get_model('rental', 'Room')
    # Revert: clear agreed_rent for rows that match price (best-effort)
    rooms = Room.objects.filter(agreed_rent__isnull=False)
    for r in rooms:
        # Only clear if agreed_rent equals price to avoid deleting negotiated differences
        try:
            if r.agreed_rent == r.price:
                r.agreed_rent = None
                r.save(update_fields=['agreed_rent'])
        except Exception:
            continue


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0007_add_room_agreed_rent'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
