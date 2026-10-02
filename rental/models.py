from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

class Building(models.Model):
    name = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Room(models.Model):
    """Room model with strict 2-tenant maximum capacity"""
    
    # System-wide maximum capacity per room
    MAX_CAPACITY = 2
    
    ROOM_TYPES = [
        ('single', 'Single'),
        ('double', 'Double'),
        ('suite', 'Suite'),
    ]
    number = models.CharField(max_length=10, unique=True)
    building = models.ForeignKey(
        Building,
        on_delete=models.PROTECT,
        related_name='rooms',
    )
    room_type = models.CharField(max_length=10, choices=ROOM_TYPES)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    agreed_rent = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Per-room negotiated rent (overrides price when set)")
    capacity = models.PositiveSmallIntegerField(default=2, help_text="Maximum number of tenants allowed in this room (max 2)")
    is_available = models.BooleanField(default=True, help_text="Manual override for room availability")
    
    class Meta:
        ordering = ['number']
    
    def __str__(self):
        return f"Room {self.number} - {self.get_room_type_display()}"

    @property
    def current_occupancy(self):
        """Returns the number of active guests currently in this room"""
        return self.guest_set.filter(is_active=True).count()

    @property
    def is_full(self):
        """Returns True if the room has reached its maximum capacity"""
        return self.current_occupancy >= self.capacity

    @property
    def is_partially_filled(self):
        """Returns True if the room has some guests but still has spare capacity"""
        occ = self.current_occupancy
        return 0 < occ < self.capacity

    @property
    def available_slots(self):
        """Returns the number of empty slots in the room"""
        return max(0, self.capacity - self.current_occupancy)

    @property
    def effective_availability(self):
        """
        Returns True if the room is both manually marked available 
        AND has not reached physical capacity.
        """
        return self.is_available and not self.is_full
    
    def clean(self):
        """Validate room capacity does not exceed system maximum"""
        super().clean()
        if self.capacity > self.MAX_CAPACITY:
            raise ValidationError({
                'capacity': f'Room capacity cannot exceed {self.MAX_CAPACITY} tenants.'
            })
        if self.capacity < 1:
            raise ValidationError({
                'capacity': 'Room capacity must be at least 1.'
            })
    
    def save(self, *args, **kwargs):
        """Enforce capacity limit on save"""
        # Cap capacity at MAX_CAPACITY
        if self.capacity > self.MAX_CAPACITY:
            self.capacity = self.MAX_CAPACITY
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_active_tenants(self):
        """Returns queryset of active guests currently in this room"""
        return self.guest_set.filter(is_active=True).select_related('room')
    
    def can_accommodate(self, count=1):
        """
        Check if room can accommodate additional tenants.
        
        Args:
            count: Number of tenants to accommodate (default: 1)
        
        Returns:
            bool: True if room has enough available slots
        """
        return self.available_slots >= count
    
    def get_occupancy_status(self):
        """Returns human-readable occupancy status"""
        occ = self.current_occupancy
        cap = self.capacity
        
        if occ == 0:
            return f"Empty (0/{cap})"
        elif occ < cap:
            return f"Partial ({occ}/{cap})"
        else:
            return f"Full ({cap}/{cap})"

class Booking(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=100)
    check_in = models.DateField()
    check_out = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-check_in']
    
    def __str__(self):
        return f"Booking: {self.customer_name} - {self.room.number}"

class Guest(models.Model):
    """Store guest/people data"""
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)  # Removed unique=True to allow shared emails
    phone = models.CharField(max_length=15, blank=True)  # Made optional
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=50, blank=True)
    state = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    id_type = models.CharField(max_length=50, blank=True, help_text="Passport, Aadhar, License, etc.")
    id_number = models.CharField(max_length=50, blank=True)
    govt_id_photo = models.ImageField(upload_to='govt_ids/', blank=True, null=True, help_text="Photo of Government ID document")
    aadhar_front = models.ImageField(upload_to='aadhar_cards/', blank=True, null=True, help_text="Aadhar Card Front Side")
    aadhar_back = models.ImageField(upload_to='aadhar_cards/', blank=True, null=True, help_text="Aadhar Card Back Side")
    college_id = models.CharField(max_length=100, blank=True, help_text="College ID or Student ID")
    college_id_photo = models.ImageField(upload_to='college_ids/', blank=True, null=True, help_text="Photo of College ID")
    student_college = models.CharField(max_length=100, blank=True, help_text="Name of the college/university")
    document_verification_image = models.ImageField(upload_to='document_verification/', blank=True, null=True, help_text="Document verification image")
    check_in_date = models.DateField(null=True, blank=True)
    check_out_date = models.DateField(null=True, blank=True)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    # Occupancy preference for the tenant
    OCCUPANCY_CHOICES = [
        ('single', 'Single (Private Room)'),
        ('double', 'Double (Shared Room)'),
    ]
    occupancy_preference = models.CharField(
        max_length=10,
        choices=OCCUPANCY_CHOICES,
        default='double',
        help_text="Tenant's occupancy preference - defaults to double occupancy"
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def roommate(self):
        """Returns the co-tenant if this guest shares a room, None otherwise"""
        if not self.room or not self.is_active:
            return None
        
        # Query for other active tenants in the same room
        roommates = Guest.objects.filter(
            room=self.room,
            is_active=True
        ).exclude(id=self.id)
        
        return roommates.first() if roommates.exists() else None
    
    def clean(self):
        """Validate guest assignment to room"""
        super().clean()
        
        # If assigning to a room, check capacity
        if self.room and self.is_active:
            # Get current occupancy excluding this guest (in case of update)
            current_occupancy = self.room.guest_set.filter(
                is_active=True
            ).exclude(id=self.id).count()
            
            # Check if room can accommodate this guest
            if current_occupancy >= self.room.capacity:
                raise ValidationError({
                    'room': f'Room {self.room.number} is full ({current_occupancy}/{self.room.capacity} tenants). Cannot assign more guests.'
                })
    
    def save(self, *args, **kwargs):
        """Auto-generate monthly payment when guest checks in"""
        from datetime import datetime
        from decimal import Decimal
        
        # Check if this is a new guest or if they're being activated
        is_new = self.pk is None
        was_inactive = False
        
        if not is_new:
            try:
                old_instance = Guest.objects.get(pk=self.pk)
                was_inactive = not old_instance.is_active and self.is_active
            except Guest.DoesNotExist:
                pass
        
        # Save the guest first
        super().save(*args, **kwargs)
        
        # Auto-generate monthly payment for current month if:
        # 1. Guest is active
        # 2. Guest has a room assigned
        # 3. Guest has a check-in date
        # 4. This is a new guest OR guest was just activated
        if self.is_active and self.room and self.check_in_date and (is_new or was_inactive):
            current_month = datetime.now().date().replace(day=1)
            
            # Check if payment already exists for this room and month
            existing_payment = MonthlyPayment.objects.filter(
                room=self.room,
                month=current_month
            ).first()
            
            if not existing_payment:
                # Create monthly payment for current month
                MonthlyPayment.objects.create(
                    room=self.room,
                    guest=self,
                    month=current_month,
                    rent_amount=self.room.price,
                    paid_amount=Decimal('0.00'),
                    payment_status='pending',
                    notes=f'Auto-generated on check-in for {self.full_name}'
                )



class MonthlyPayment(models.Model):
    """Track monthly rent payments for each room/tenant"""
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='monthly_payments')
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name='monthly_payments')
    month = models.DateField(help_text="First day of the month")
    rent_amount = models.DecimalField(max_digits=8, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    paid_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-month']
        unique_together = ('room', 'month')
    
    def __str__(self):
        return f"{self.room.number} - {self.month.strftime('%B %Y')} - {self.payment_status}"
    
    def remaining_amount(self):
        """Calculate remaining rent amount (without electricity)"""
        return self.rent_amount - self.paid_amount
    
    def get_electricity_amount(self):
        """Get electricity bill amount for this month"""
        from decimal import Decimal
        try:
            # Get electricity bill for this room and month
            bill = self.room.electricity_bills.filter(month=self.month).first()
            if bill:
                return Decimal(str(bill.bill_amount))
            return Decimal('0.00')
        except Exception:
            return Decimal('0.00')
    
    def get_total_amount_due(self):
        """Calculate total amount due including rent and electricity"""
        return self.rent_amount + self.get_electricity_amount()
    
    def get_total_remaining(self):
        """Calculate total remaining amount including electricity"""
        return self.get_total_amount_due() - self.paid_amount


class PaymentRecord(models.Model):
    """Maintain detailed payment history for each payment"""
    monthly_payment = models.ForeignKey(MonthlyPayment, on_delete=models.CASCADE, related_name='payment_records')
    payment_date = models.DateField()
    payment_amount = models.DecimalField(max_digits=8, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=[
        ('cash', 'Cash'),
        ('check', 'Check'),
        ('bank_transfer', 'Bank Transfer'),
        ('upi', 'UPI'),
        ('card', 'Card'),
    ], default='cash')
    reference_number = models.CharField(max_length=100, blank=True, help_text="Check/Transaction number")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"{self.monthly_payment.room.number} - ₹{self.payment_amount} - {self.payment_date}"


class ElectricityBill(models.Model):
    """Track electricity consumption and bills"""
    BILL_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='electricity_bills')
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name='electricity_bills')
    month = models.DateField(help_text="First day of the month")
    starting_reading = models.DecimalField(max_digits=10, decimal_places=2, help_text="Meter reading at start")
    ending_reading = models.DecimalField(max_digits=10, decimal_places=2, help_text="Meter reading at end")
    units_consumed = models.DecimalField(max_digits=8, decimal_places=2)
    rate_per_unit = models.DecimalField(max_digits=6, decimal_places=2, help_text="Cost per unit in ₹")
    bill_amount = models.DecimalField(max_digits=8, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    bill_status = models.CharField(max_length=20, choices=BILL_STATUS_CHOICES, default='pending')
    bill_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-month']
        unique_together = ('room', 'month')
    
    def __str__(self):
        return f"{self.room.number} - {self.month.strftime('%B %Y')} - ₹{self.bill_amount}"
    
    def remaining_amount(self):
        return self.bill_amount - self.paid_amount

class MaintenanceExpense(models.Model):
    """Track maintenance and other expenses for buildings"""
    EXPENSE_CATEGORIES = [
        ('plumbing', 'Plumbing'),
        ('electrical', 'Electrical'),
        ('painting', 'Painting'),
        ('carpentry', 'Carpentry'),
        ('cleaning', 'Cleaning'),
        ('repairs', 'General Repairs'),
        ('security', 'Security'),
        ('internet', 'Internet/WiFi'),
        ('other', 'Other'),
    ]
    
    building_name = models.CharField(max_length=50, help_text="e.g., M1, 1, 2, etc.")
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES, default='other')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    description = models.TextField()
    is_paid = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.building_name} - {self.get_category_display()} - ₹{self.amount}"
