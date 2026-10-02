from django.core.management.base import BaseCommand
from rental.models import Guest, MonthlyPayment, PaymentRecord, ElectricityBill, Room

class Command(BaseCommand):
    help = 'Wipes all tenant, payment, and bill data but KEEPS Rooms and Admin users.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('⚠️  STARTING FORCE DATA RESET...'))
        
        # 1. Delete Guests (Cascades to Payments usually, but we will be explicit)
        count_guests = Guest.objects.all().count()
        Guest.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'✓ Deleted {count_guests} Guests'))
        
        # 2. Delete Orphaned Payments/Bills (if any remain)
        MonthlyPayment.objects.all().delete()
        PaymentRecord.objects.all().delete()
        ElectricityBill.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('✓ Cleared all Financial Records'))
        
        # 3. Reset Room Status
        Room.objects.update(is_available=True)
        # Note: current_occupancy is a property, so it will naturally be 0 when guests are gone.
        self.stdout.write(self.style.SUCCESS('✓ Reset all Rooms to Available'))
        
        self.stdout.write(self.style.SUCCESS('\n✅  DATABASE RESET COMPLETE. Ready for fresh data.'))
