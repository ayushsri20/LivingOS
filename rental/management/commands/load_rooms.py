from django.core.management.base import BaseCommand
from rental.models import Building, Room


class Command(BaseCommand):
    help = 'Load sample rooms for all 6 buildings (36 total rooms)'

    def handle(self, *args, **options):
        """Create 36 rooms across 6 buildings (M1, 1-5) with 6 rooms each"""
        
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
        
        all_rooms = (
            [(number, room_type, price, 'M1') for number, room_type, price in m1_rooms]
            + [(number, room_type, price, '1') for number, room_type, price in building1_rooms]
            + [(number, room_type, price, '2') for number, room_type, price in building2_rooms]
            + [(number, room_type, price, '3') for number, room_type, price in building3_rooms]
            + [(number, room_type, price, '4') for number, room_type, price in building4_rooms]
            + [(number, room_type, price, '5') for number, room_type, price in building5_rooms]
        )
        
        created_count = 0
        skipped_count = 0
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Creating 36 Rooms Across 6 Buildings'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
        
        for room_number, room_type, price, building_name in all_rooms:
            if not Room.objects.filter(number=room_number).exists():
                Room.objects.create(
                    number=room_number,
                    building=Building.objects.get(name=building_name),
                    room_type=room_type,
                    price=price,
                    is_available=True
                )
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created room {room_number} ({room_type}, ₹{price})")
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f"- Skipped {room_number} (already exists)")
                )
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Summary:'))
        self.stdout.write(self.style.SUCCESS(f"  Created: {created_count} rooms"))
        self.stdout.write(self.style.WARNING(f"  Skipped: {skipped_count} rooms (already exist)"))
        self.stdout.write(self.style.SUCCESS(f"  Total in database: {Room.objects.count()} rooms"))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
