"""
Data migration to cap all room capacities at 2 tenants and report any issues.
"""
from django.db import migrations

def cap_room_capacities(apps, schema_editor):
    """Cap all room capacities at 2 and report any rooms with >2 active tenants"""
    Room = apps.get_model('rental', 'Room')
    Guest = apps.get_model('rental', 'Guest')
    
    updated_count = 0
    problem_rooms = []
    
    # Update all rooms with capacity > 2
    for room in Room.objects.filter(capacity__gt=2):
        old_capacity = room.capacity
        room.capacity = 2
        room.save()
        updated_count += 1
        
        # Check if this room has more than 2 active tenants
        active_tenants = Guest.objects.filter(room=room, is_active=True).count()
        if active_tenants > 2:
            problem_rooms.append({
                'room_number': room.number,
                'old_capacity': old_capacity,
                'active_tenants': active_tenants
            })
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Room Capacity Migration Summary")
    print(f"{'='*60}")
    print(f"✅ Updated {updated_count} rooms to capacity=2")
    
    if problem_rooms:
        print(f"\n⚠️  WARNING: {len(problem_rooms)} rooms have MORE than 2 active tenants:")
        print(f"{'='*60}")
        for room in problem_rooms:
            print(f"  Room {room['room_number']}: {room['active_tenants']} tenants (was capacity {room['old_capacity']})")
        print(f"\n⚠️  ACTION REQUIRED: Manually reassign excess tenants!")
    else:
        print(f"\n✅ No rooms with >2 active tenants found")
    
    print(f"{'='*60}\n")

def reverse_cap(apps, schema_editor):
    """Reverse migration - restore original capacities (not recommended)"""
    print("⚠️  Reverse migration: Room capacities remain at 2 (original values not stored)")

class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0012_cap_room_capacity_at_2'),
    ]


    operations = [
        migrations.RunPython(cap_room_capacities, reverse_cap),
    ]
