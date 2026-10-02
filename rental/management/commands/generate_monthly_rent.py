from django.core.management.base import BaseCommand
from rental.models import Room, Guest, MonthlyPayment
from datetime import datetime
from decimal import Decimal


class Command(BaseCommand):
    help = 'Generate monthly rent payments for all active guests (run on 1st of each month)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--month',
            type=str,
            help='Month to generate payments for (YYYY-MM-DD format, defaults to current month)',
        )

    def handle(self, *args, **options):
        """
        Generate monthly rent payments for all active guests.
        This should be run automatically on the 1st of each month via cron job.
        """
        
        # Determine which month to generate payments for
        if options['month']:
            try:
                payment_month = datetime.strptime(options['month'], '%Y-%m-%d').date().replace(day=1)
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
                return
        else:
            payment_month = datetime.now().date().replace(day=1)
        
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'GENERATING MONTHLY RENT FOR {payment_month.strftime("%B %Y")}'))
        self.stdout.write(self.style.SUCCESS('=' * 60 + '\n'))
        
        # Get all active guests
        active_guests = Guest.objects.filter(is_active=True).select_related('room')
        
        created_count = 0
        skipped_count = 0
        
        for guest in active_guests:
            # Check if payment already exists for this room and month
            existing_payment = MonthlyPayment.objects.filter(
                room=guest.room,
                month=payment_month
            ).first()
            
            if existing_payment:
                self.stdout.write(
                    self.style.WARNING(
                        f"⏭️  Room {guest.room.number} ({guest.full_name}): Already exists"
                    )
                )
                skipped_count += 1
            else:
                # Create monthly payment with room's agreed rent
                MonthlyPayment.objects.create(
                    room=guest.room,
                    guest=guest,
                    month=payment_month,
                    rent_amount=guest.room.price,  # Use room's price as rent amount
                    paid_amount=Decimal('0.00'),
                    payment_status='pending',
                    notes=f'Auto-generated monthly rent for {payment_month.strftime("%B %Y")}'
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Room {guest.room.number} ({guest.full_name}): Created ₹{guest.room.price}"
                    )
                )
                created_count += 1
        
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'Month: {payment_month.strftime("%B %Y")}'))
        self.stdout.write(self.style.SUCCESS(f'Payments Created: {created_count}'))
        self.stdout.write(self.style.WARNING(f'Payments Skipped: {skipped_count}'))
        self.stdout.write(self.style.SUCCESS(f'Total Active Guests: {active_guests.count()}'))
        self.stdout.write(self.style.SUCCESS('=' * 60 + '\n'))
        
        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Successfully generated {created_count} monthly rent payments!'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  No new payments created. All active guests already have payments for this month.'
                )
            )
