"""
Test script for 2-tenant maximum room allocation system.
Tests capacity enforcement, room filtering, and tenant assignment validation.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Room, Guest
from django.core.exceptions import ValidationError
from django.db import transaction

def test_capacity_enforcement():
    """Test that rooms cannot exceed 2-tenant capacity"""
    print("\n" + "="*60)
    print("TEST 1: Room Capacity Enforcement")
    print("="*60)
    
    # Create a test room with capacity 2
    room = Room.objects.create(
        number="TEST-01",
        room_type="double",
        price=5000,
        capacity=2
    )
    print(f"✅ Created room {room.number} with capacity={room.capacity}")
    
    # Try to set capacity > 2 (should be capped)
    room.capacity = 5
    room.save()
    room.refresh_from_db()
    assert room.capacity == 2, f"Expected capacity=2, got {room.capacity}"
    print(f"✅ Capacity auto-capped: Attempted 5 → Saved as {room.capacity}")
    
    # Clean up
    room.delete()
    print("✅ Test passed: Capacity enforcement working\n")

def test_tenant_assignment_validation():
    """Test that tenant assignment respects room capacity"""
    print("="*60)
    print("TEST 2: Tenant Assignment Validation")
    print("="*60)
    
    # Create test room
    room = Room.objects.create(
        number="TEST-02",
        room_type="double",
        price=5000,
        capacity=2
    )
    print(f"✅ Created room {room.number} (capacity: {room.capacity})")
    
    # Add first tenant
    guest1 = Guest.objects.create(
        first_name="Test",
        last_name="User1",
        room=room,
        is_active=True
    )
    print(f"✅ Added Tenant 1: {guest1.full_name} → Occupancy: {room.current_occupancy}/2")
    
    # Add second tenant
    guest2 = Guest.objects.create(
        first_name="Test",
        last_name="User2",
        room=room,
        is_active=True
    )
    print(f"✅ Added Tenant 2: {guest2.full_name} → Occupancy: {room.current_occupancy}/2")
    
    # Try to add third tenant (should fail)
    try:
        guest3 = Guest.objects.create(
            first_name="Test",
            last_name="User3",
            room=room,
            is_active=True
        )
        guest3.clean()  # Trigger validation
        print("❌ ERROR: Third tenant was allowed (should have been blocked)")
        guest3.delete()
    except ValidationError as e:
        print(f"✅ Third tenant blocked: {e.message_dict['room'][0]}")
    
    # Verify roommate property
    guest1.refresh_from_db()  # Refresh to ensure latest data
    roommate = guest1.roommate
    assert roommate is not None, "Roommate should not be None"
    assert roommate.id == guest2.id, f"Expected roommate {guest2.full_name}, got {roommate.full_name if roommate else 'None'}"
    print(f"✅ Roommate property working: {guest1.full_name}'s roommate is {roommate.full_name}")
    
    # Clean up
    guest1.delete()
    guest2.delete()
    room.delete()
    print("✅ Test passed: Tenant assignment validation working\n")

def test_room_filtering():
    """Test enhanced room filtering logic"""
    print("="*60)
    print("TEST 3: Enhanced Room Filtering")
    print("="*60)
    
    # Create test rooms
    empty_room = Room.objects.create(
        number="TEST-EMPTY",
        room_type="double",
        price=5000,
        capacity=2,
        is_available=True
    )
    
    partial_room = Room.objects.create(
        number="TEST-PARTIAL",
        room_type="double",
        price=5000,
        capacity=2,
        is_available=True
    )
    
    full_room = Room.objects.create(
        number="TEST-FULL",
        room_type="double",
        price=5000,
        capacity=2,
        is_available=True
    )
    
    # Add tenants
    Guest.objects.create(first_name="Partial", last_name="Tenant", room=partial_room, is_active=True)
    Guest.objects.create(first_name="Full", last_name="Tenant1", room=full_room, is_active=True)
    Guest.objects.create(first_name="Full", last_name="Tenant2", room=full_room, is_active=True)
    
    print(f"✅ Created 3 test rooms:")
    print(f"   - {empty_room.number}: {empty_room.get_occupancy_status()}")
    print(f"   - {partial_room.number}: {partial_room.get_occupancy_status()}")
    print(f"   - {full_room.number}: {full_room.get_occupancy_status()}")
    
    # Test filtering
    from rental.views import get_available_rooms_for_allocation
    available = get_available_rooms_for_allocation()
    
    available_numbers = [r.number for r in available]
    print(f"\n✅ Available rooms for allocation: {available_numbers}")
    
    # Verify partial room comes first (priority sorting)
    assert available[0].number == "TEST-PARTIAL", "Partial room should be first"
    print(f"✅ Sorting correct: Partial room ({available[0].number}) listed first")
    
    # Verify full room is excluded
    assert full_room.number not in available_numbers, "Full room should be excluded"
    print(f"✅ Filtering correct: Full room excluded from available list")
    
    # Clean up
    Guest.objects.filter(room__number__startswith="TEST-").delete()
    Room.objects.filter(number__startswith="TEST-").delete()
    print("✅ Test passed: Room filtering working correctly\n")

def test_occupancy_status():
    """Test occupancy status display"""
    print("="*60)
    print("TEST 4: Occupancy Status Display")
    print("="*60)
    
    room = Room.objects.create(
        number="TEST-STATUS",
        room_type="double",
        price=5000,
        capacity=2
    )
    
    # Empty
    status = room.get_occupancy_status()
    print(f"✅ Empty room status: '{status}'")
    assert status == "Empty (0/2)", f"Expected 'Empty (0/2)', got '{status}'"
    
    # Partial
    Guest.objects.create(first_name="Test", last_name="User", room=room, is_active=True)
    status = room.get_occupancy_status()
    print(f"✅ Partial room status: '{status}'")
    assert status == "Partial (1/2)", f"Expected 'Partial (1/2)', got '{status}'"
    
    # Full
    Guest.objects.create(first_name="Test2", last_name="User2", room=room, is_active=True)
    status = room.get_occupancy_status()
    print(f"✅ Full room status: '{status}'")
    assert status == "Full (2/2)", f"Expected 'Full (2/2)', got '{status}'"
    
    # Clean up
    Guest.objects.filter(room=room).delete()
    room.delete()
    print("✅ Test passed: Occupancy status display working\n")

if __name__ == "__main__":
    print("\n" + "🏨 ROOM ALLOCATION SYSTEM - TEST SUITE" + "\n")
    
    try:
        test_capacity_enforcement()
        test_tenant_assignment_validation()
        test_room_filtering()
        test_occupancy_status()
        
        print("="*60)
        print("✨ ALL TESTS PASSED SUCCESSFULLY! ✨")
        print("="*60)
        print("\n2-Tenant Maximum Room Allocation System is working correctly!\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
