from django.contrib import admin
from .models import Building, Room, Booking, Guest, MonthlyPayment, PaymentRecord, ElectricityBill

@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('number', 'building', 'room_type', 'price', 'agreed_rent', 'is_available')
    list_filter = ('building', 'room_type', 'is_available')
    search_fields = ('number', 'building__name')
    fields = ('number', 'building', 'room_type', 'price', 'agreed_rent', 'is_available')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'room', 'check_in', 'check_out', 'is_active', 'created_by')
    list_filter = ('is_active', 'check_in')
    search_fields = ('customer_name',)
    fields = ('room', 'customer_name', 'check_in', 'check_out', 'created_by', 'is_active')

@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone', 'room', 'check_in_date', 'is_active')
    list_filter = ('is_active', 'gender', 'check_in_date')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'gender', 'date_of_birth')
        }),
        ('Address', {
            'fields': ('address', 'city', 'state', 'country', 'zip_code'),
            'classes': ('collapse',)
        }),
        ('Identification', {
            'fields': ('id_type', 'id_number'),
            'classes': ('collapse',)
        }),
        ('Room & Stay', {
            'fields': ('room', 'check_in_date', 'check_out_date', 'notes')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )

@admin.register(MonthlyPayment)
class MonthlyPaymentAdmin(admin.ModelAdmin):
    list_display = ('room', 'month', 'rent_amount', 'paid_amount', 'payment_status', 'paid_date')
    list_filter = ('payment_status', 'month', 'room')
    search_fields = ('room__number',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Payment Details', {
            'fields': ('room', 'guest', 'month')
        }),
        ('Amount', {
            'fields': ('rent_amount', 'paid_amount', 'payment_status')
        }),
        ('Dates', {
            'fields': ('paid_date', 'created_at', 'updated_at')
        }),
        ('Additional', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )

@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('get_room', 'payment_date', 'payment_amount', 'payment_method', 'reference_number')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('monthly_payment__room__number', 'reference_number')
    readonly_fields = ('created_at', 'created_by')
    fields = ('monthly_payment', 'payment_date', 'payment_amount', 'payment_method', 'reference_number', 'notes', 'created_by', 'created_at')
    
    def get_room(self, obj):
        return obj.monthly_payment.room.number
    get_room.short_description = 'Room'

@admin.register(ElectricityBill)
class ElectricityBillAdmin(admin.ModelAdmin):
    list_display = ('room', 'month', 'units_consumed', 'bill_amount', 'paid_amount', 'bill_status', 'due_date')
    list_filter = ('bill_status', 'month', 'room')
    search_fields = ('room__number',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Bill Details', {
            'fields': ('room', 'guest', 'month')
        }),
        ('Meter Readings', {
            'fields': ('starting_reading', 'ending_reading', 'units_consumed')
        }),
        ('Billing', {
            'fields': ('rate_per_unit', 'bill_amount', 'paid_amount', 'bill_status')
        }),
        ('Dates', {
            'fields': ('bill_date', 'due_date', 'paid_date', 'created_at', 'updated_at')
        }),
        ('Additional', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
