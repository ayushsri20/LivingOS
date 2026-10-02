#!/usr/bin/env python3
"""
Sample data loader for Panesar PG Hotel Management System
Run this to populate the database with sample rooms
Creates 36 rooms across 6 buildings (M1, 1, 2, 3, 4, 5)
"""

import os
import sys
import django

# Setup Django environment - works both locally and on Railway
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, '/app')  # Fallback for Railway

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Room

def create_sample_rooms():
    """Create sample rooms for all 6 buildings with 6 rooms each = 36 total rooms"""
    
    # M1 Complex (A) - Premium building
    m1_rooms = [
        ('A-101', 'single', 7500),
        ('A-102', 'single', 7500),
        ('A-103', 'double', 8000),
        ('A-104', 'double', 8000),
        ('A-105', 'suite', 7000),
        ('A-106', 'single', 7000),
    ]
    
    # Building 1 (B) - 6 rooms
    building1_rooms = [
        ('B-101', 'single', 7000),
        ('B-102', 'single', 7000),
        ('B-103', 'double', 7000),
        ('B-104', 'double', 7000),
        ('B-105', 'single', 7000),
        ('B-106', 'single', 7000),
    ]
    
    # Building 2 (C) - 6 rooms
    building2_rooms = [
        ('C-101', 'single', 7000),
        ('C-102', 'single', 7000),
        ('C-103', 'double', 7000),
        ('C-104', 'double', 7000),
        ('C-105', 'single', 7000),
        ('C-106', 'suite', 7000),
    ]
    
    # Building 3 (D) - 6 rooms
    building3_rooms = [
        ('D-101', 'single', 7000),
        ('D-102', 'single', 7000),
        ('D-103', 'double', 7000),
        ('D-104', 'double', 7000),
        ('D-105', 'single', 7000),
        ('D-106', 'single', 7000),
    ]
    
    # Building 4 (E) - 6 rooms
    building4_rooms = [
        ('E-101', 'single', 7000),
        ('E-102', 'single', 7000),
        ('E-103', 'double', 7000),
        ('E-104', 'double', 7000),
        ('E-105', 'single', 7000),
        ('E-106', 'single', 7000),
    ]
    
    # Building 5 (F) - 6 rooms
    building5_rooms = [
        ('F-101', 'single', 7000),
        ('F-102', 'single', 7000),
        ('F-103', 'double', 7000),
        ('F-104', 'double', 7000),
        ('F-105', 'single', 7000),
        ('F-106', 'single', 7000),
    ]
    
    all_rooms = (m1_rooms + building1_rooms + building2_rooms + 
                 building3_rooms + building4_rooms + building5_rooms)
    
    created_count = 0
    skipped_count = 0
    
    print(f"\n{'='*60}")
    print(f"Creating 36 Rooms Across 6 Buildings")
    print(f"{'='*60}\n")
    
    for room_number, room_type, price in all_rooms:
        if not Room.objects.filter(number=room_number).exists():
            Room.objects.create(
                number=room_number,
                room_type=room_type,
                price=price,
                is_available=True
            )
            created_count += 1
            print(f"✓ Created room {room_number} ({room_type}, ₹{price})")
        else:
            skipped_count += 1
            print(f"- Skipped {room_number} (already exists)")
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Created: {created_count} rooms")
    print(f"  Skipped: {skipped_count} rooms (already exist)")
    print(f"  Total in database: {Room.objects.count()} rooms")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    create_sample_rooms()
