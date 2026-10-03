from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import Building, Room, ElectricityBill, Guest, MonthlyPayment, PaymentRecord
from django.core.files.uploadedfile import SimpleUploadedFile
import json


@override_settings(
    MIDDLEWARE=[m for m in settings.MIDDLEWARE if 'LoginRequiredMiddleware' not in m],
    APPEND_SLASH=False,
    ELECTRICITY_RATE_PER_UNIT='13.00',
)
class RoomFirstBillingApiTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='billing-admin',
            email='billing-admin@example.com',
            password='password',
        )
        self.building = Building.objects.get(name='M1')
        self.room = Room.objects.create(
            number='Z-001',
            building=self.building,
            room_type='single',
            price='8000.00',
            agreed_rent='7500.00',
            is_available=True,
        )
        self.client.force_login(self.admin)
        self.month = timezone.now().date().replace(day=1)
        self.previous_month = (self.month - timedelta(days=1)).replace(day=1)
        self.historical_bill = ElectricityBill.objects.create(
            room=self.room,
            month=self.previous_month,
            starting_reading='50.00',
            ending_reading='64.00',
            units_consumed='14.00',
            rate_per_unit='13.00',
            bill_amount='182.00',
            due_date=self.previous_month,
        )

    def test_room_billing_and_payment_flow_is_backend_authoritative(self):
        Guest.objects.create(first_name='Roommate', last_name='One', room=self.room, is_active=True)
        Guest.objects.create(first_name='Roommate', last_name='Two', room=self.room, is_active=True)

        monthly_count = MonthlyPayment.objects.count()
        room_list = self.client.get(reverse('api_rooms'))
        self.assertEqual(room_list.status_code, 200)
        self.assertEqual(room_list.json()['rooms'][0]['building'], 'M1')
        self.assertEqual(room_list.json()['rooms'][0]['new_bill_rate'], 13)
        self.assertEqual(MonthlyPayment.objects.count(), monthly_count)
        self.assertEqual(room_list.json()['rooms'][0]['payment_status'], 'DUE')
        dashboard = self.client.get(reverse('dashboard'))
        self.assertContains(dashboard, f'{reverse("manage_buildings")}?room_id={self.room.id}')
        self.assertContains(dashboard, 'Analytics Overview')
        self.assertContains(dashboard, 'Receivable')
        self.assertContains(dashboard, reverse('performance_dashboard'))
        self.assertContains(dashboard, 'class="ro-building ro-card"')
        self.assertContains(dashboard, 'Roommate')
        rooms_page = self.client.get(reverse('manage_buildings'))
        self.assertContains(rooms_page, 'Choose a building, open a room')
        self.assertContains(rooms_page, 'data-api-root="/api/rooms/"')

        url = reverse('api_generate_bill', args=[self.room.id])

        for invalid_reading in ('-1', '63', '98.001'):
            response = self.client.post(
                url,
                data=json.dumps({'current_reading': invalid_reading}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 400)
        response = self.client.post(
            url,
            data=json.dumps({'current_reading': '98', 'electricity_rate': '-17'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ElectricityBill.objects.filter(room=self.room, month=self.month).exists())

        response = self.client.post(
            url,
            data=json.dumps({'current_reading': '98'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        generated = response.json()
        self.assertEqual(generated['units_used'], 34)
        self.assertEqual(generated['electricity_amount'], 442)
        self.assertEqual(generated['agreed_rent'], 7500)
        self.assertEqual(generated['total_bill'], 7942)

        bill = ElectricityBill.objects.get(room=self.room, month=self.month)
        repeated_response = self.client.post(
            url,
            data=json.dumps({'current_reading': '98'}),
            content_type='application/json',
        )
        self.assertEqual(repeated_response.status_code, 200)
        self.assertEqual(repeated_response.json()['bill']['id'], bill.id)
        self.assertEqual(repeated_response.json()['total_bill'], 7942)
        self.assertEqual(bill.starting_reading, 64)
        self.assertEqual(bill.ending_reading, 98)
        self.assertEqual(bill.units_consumed, 34)
        self.assertEqual(bill.bill_amount, 442)
        self.historical_bill.refresh_from_db()
        self.assertEqual(self.historical_bill.ending_reading, 64)

        collect_url = reverse('api_collect_payment', args=[self.room.id])
        response = self.client.post(
            collect_url,
            data=json.dumps({'amount': '5000', 'payment_status': 'PAID'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        first_collection = response.json()
        self.assertEqual(first_collection['total_bill'], 7942)
        self.assertEqual(first_collection['collected_amount'], 5000)
        self.assertEqual(first_collection['outstanding_amount'], 2942)
        self.assertEqual(first_collection['payment_status'], 'PARTIAL')

        payment_url = reverse('api_room_payments', args=[self.room.id])
        history_response = self.client.get(payment_url)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(len(history_response.json()['payments']), 1)

        detail = self.client.get(reverse('api_room_detail', args=[self.room.id])).json()['room']
        current_bill = self.client.get(reverse('api_current_bill', args=[self.room.id])).json()
        self.assertEqual(detail['total_bill'], 7942)
        self.assertEqual(detail['outstanding_amount'], 2942)
        self.assertEqual(current_bill['payment_status'], 'PARTIAL')

        metrics_response = self.client.get(reverse('dashboard_metrics_api')).json()
        metrics = metrics_response['metrics']
        self.assertGreater(metrics['expected_yield'], 0)
        self.assertEqual(metrics['realized_revenue'], 5000)
        self.assertGreater(metrics['accounts_receivable'], 0)
        self.assertEqual(metrics_response['meta']['occupied_rooms'], 1)

        performance = self.client.get(reverse('performance_dashboard'))
        self.assertEqual(performance.status_code, 200)
        self.assertContains(performance, 'Z-001')
        self.assertContains(performance, '7942.0')
        self.assertContains(performance, '₹5000 / ₹7942')
        self.assertContains(performance, '₹2942')
        self.assertContains(performance, '100%')

        response = self.client.post(
            collect_url,
            data=json.dumps({'amount': '-1'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            collect_url,
            data=json.dumps({'amount': '0.001'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PaymentRecord.objects.filter(monthly_payment__room=self.room).count(), 1)

        response = self.client.post(
            collect_url,
            data=json.dumps({'amount': '2942'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        final_collection = response.json()
        self.assertEqual(final_collection['collected_amount'], 7942)
        self.assertEqual(final_collection['outstanding_amount'], 0)
        self.assertEqual(final_collection['payment_status'], 'PAID')
        self.assertEqual(len(self.client.get(payment_url).json()['payments']), 2)

        monthly_payment = MonthlyPayment.objects.get(room=self.room, month=self.month)
        self.assertEqual(monthly_payment.paid_amount, 7942)
        self.assertEqual(monthly_payment.payment_status, 'paid')

    def test_new_room_bill_uses_thirteen_per_unit_and_adds_agreed_rent(self):
        response = self.client.post(
            reverse('api_generate_bill', args=[self.room.id]),
            data=json.dumps({'current_reading': '114'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        generated = response.json()
        bill = ElectricityBill.objects.get(room=self.room, month=self.month)
        self.assertEqual(generated['units_used'], 50)
        self.assertEqual(generated['electricity_rate'], 13)
        self.assertEqual(generated['electricity_amount'], 650)
        self.assertEqual(generated['agreed_rent'], 7500)
        self.assertEqual(generated['total_bill'], 8150)
        self.assertEqual(bill.rate_per_unit, 13)
        self.assertEqual(bill.bill_amount, 650)

    def test_regenerating_does_not_change_an_existing_bill_at_another_rate(self):
        existing_bill = ElectricityBill.objects.create(
            room=self.room,
            month=self.month,
            starting_reading='64.00',
            ending_reading='80.00',
            units_consumed='16.00',
            rate_per_unit='17.00',
            bill_amount='272.00',
            due_date=self.month,
        )

        response = self.client.post(
            reverse('api_generate_bill', args=[self.room.id]),
            data=json.dumps({'current_reading': '114'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 409)
        existing_bill.refresh_from_db()
        self.assertEqual(existing_bill.ending_reading, 80)
        self.assertEqual(existing_bill.units_consumed, 16)
        self.assertEqual(existing_bill.rate_per_unit, 17)
        self.assertEqual(existing_bill.bill_amount, 272)
        room_snapshot = self.client.get(
            reverse('api_room_detail', args=[self.room.id])
        ).json()['room']
        self.assertEqual(room_snapshot['electricity_rate'], 17)
        self.assertEqual(room_snapshot['new_bill_rate'], 13)

    def test_room_tenant_api_uses_existing_guest_document_fields(self):
        guest = Guest.objects.create(
            first_name='Document',
            last_name='Tenant',
            room=self.room,
            is_active=True,
            id_type='Passport',
            id_number='P123456',
            college_id='STU-123',
            student_college='Example College',
        )

        response = self.client.get(reverse('get_room_tenants', args=[self.room.id]))

        self.assertEqual(response.status_code, 200)
        tenant = response.json()['tenants'][0]
        self.assertEqual(tenant['id'], guest.id)
        self.assertEqual(tenant['name'], 'Document Tenant')
        self.assertEqual(tenant['college_id'], 'STU-123')
        self.assertEqual(tenant['student_college'], 'Example College')
        self.assertIsNone(tenant['govt_id_photo'])
        self.assertIsNone(tenant['aadhar_front'])
        self.assertIsNone(tenant['aadhar_back'])
        self.assertIsNone(tenant['college_id_photo'])
        self.assertIsNone(tenant['document_verification_image'])

    def test_building_and_billing_pages_render_without_server_errors(self):
        route_names = (
            'login',
            'dashboard',
            'dashboard_metrics_api',
            'api_rooms',
            'manage_buildings',
            'manage_guests',
            'manage_payments',
            'manage_electricity_bills',
            'performance_dashboard',
            'booking_page',
        )
        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                expected_status = 302 if route_name == 'login' else 200
                self.assertEqual(response.status_code, expected_status)


class FreshDatabaseRoomInventoryMigrationTests(TestCase):
    def test_fresh_database_has_one_complete_authoritative_inventory(self):
        self.assertEqual(
                list(Building.objects.order_by('id').values_list('name', flat=True)),
                ['M1', '1', '2', '3', '4', '5'],
        )
        self.assertEqual(Room.objects.count(), 36)
        for building in Building.objects.all():
                with self.subTest(building=building.name):
                    self.assertEqual(building.rooms.count(), 6)
        self.assertFalse(Room.objects.filter(building__isnull=True).exists())
        self.assertEqual(Room.objects.filter(number='A-101').count(), 1)


@override_settings(
    MIDDLEWARE=[m for m in settings.MIDDLEWARE if 'LoginRequiredMiddleware' not in m],
    APPEND_SLASH=False
)
class ElectricityBillFormTests(TestCase):
    def setUp(self):
        User = get_user_model()
        # create admin user
        self.admin = User.objects.create_superuser(username='admin', email='admin@example.com', password='password')
        # create a sample room
        self.building = Building.objects.get(name='M1')
        self.room = Room.objects.get(number='A-101')
        # Login the client
        self.client.force_login(self.admin)

    def test_create_bill_with_month_yyyy_mm(self):
        url = reverse('create_electricity_bill')
        data = {
            'room_id': str(self.room.id),
            'month': '2025-11',
            'starting_reading': '100.0',
            'ending_reading': '150.0',
            'rate_per_unit': '13',
            'due_date': '2025-11-20'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        resp = json.loads(response.content)
        self.assertTrue(resp.get('success'))
        # bill should be created
        bill = ElectricityBill.objects.filter(room=self.room).first()
        self.assertIsNotNone(bill)
        self.assertEqual(bill.units_consumed, 50.0)
        self.assertEqual(bill.rate_per_unit, 13)
        self.assertEqual(bill.bill_amount, 650)

    def test_create_bill_rejects_non_configured_rate(self):
        response = self.client.post(reverse('create_electricity_bill'), {
            'room_id': str(self.room.id),
            'month': '2025-12',
            'starting_reading': '100.0',
            'ending_reading': '150.0',
            'rate_per_unit': '17',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ElectricityBill.objects.filter(room=self.room, month='2025-12-01').exists())

    def test_single_room_generator_uses_configured_rate(self):
        month = timezone.now().date().replace(day=1)
        previous_month = (month - timedelta(days=1)).replace(day=1)
        ElectricityBill.objects.create(
            room=self.room,
            month=previous_month,
            starting_reading='50.00',
            ending_reading='64.00',
            units_consumed='14.00',
            rate_per_unit='13.00',
            bill_amount='182.00',
            due_date=previous_month,
        )
        response = self.client.post(reverse('generate_single_room_bill'), {
            'room_id': str(self.room.id),
            'month': month.strftime('%Y-%m'),
            'ending_reading': '114',
            'rate_per_unit': '13',
        })

        self.assertEqual(response.status_code, 200)
        bill = ElectricityBill.objects.get(room=self.room, month=month)
        self.assertEqual(bill.units_consumed, 50)
        self.assertEqual(bill.rate_per_unit, 13)
        self.assertEqual(bill.bill_amount, 650)

    def test_bulk_generator_uses_configured_rate(self):
        month = timezone.now().date().replace(day=1)
        response = self.client.post(reverse('bulk_create_electricity_bills'), {
            'month': month.strftime('%Y-%m'),
            'rate_per_unit': '13',
            'readings': json.dumps([{
                'room_id': self.room.id,
                'starting_reading': '64',
                'ending_reading': '114',
            }]),
        })

        self.assertEqual(response.status_code, 200)
        bill = ElectricityBill.objects.get(room=self.room, month=month)
        self.assertEqual(bill.units_consumed, 50)
        self.assertEqual(bill.rate_per_unit, 13)
        self.assertEqual(bill.bill_amount, 650)

    def test_create_bill_missing_month(self):
        url = reverse('create_electricity_bill')
        data = {
            'room_id': str(self.room.id),
            'starting_reading': '100.0',
            'ending_reading': '150.0',
            'rate_per_unit': '13',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        resp = json.loads(response.content)
        self.assertFalse(resp.get('success'))

    def test_create_bill_ending_less_than_start(self):
        url = reverse('create_electricity_bill')
        data = {
            'room_id': str(self.room.id),
            'month': '2025-11',
            'starting_reading': '200.0',
            'ending_reading': '150.0',
            'rate_per_unit': '13',
            'due_date': '2025-11-20'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        resp = json.loads(response.content)
        self.assertFalse(resp.get('success'))


@override_settings(
    MIDDLEWARE=[m for m in settings.MIDDLEWARE if 'LoginRequiredMiddleware' not in m],
    APPEND_SLASH=False
)
class GuestFileUploadTests(TestCase):
    """Test file upload functionality for guest documents"""
    
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username='admin', email='admin@test.com', password='password')
        self.building = Building.objects.get(name='1')
        self.room = Room.objects.get(number='B-101')
        self.client.force_login(self.admin)
    
    def test_add_guest_with_govt_id_photo(self):
        """Test adding guest with ID proof image"""
        
        # Create a small test image
        image_content = b'fake image content'
        test_image = SimpleUploadedFile(
            "id_proof.jpg",
            image_content,
            content_type="image/jpeg"
        )
        
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@test.com',
            'phone': '9876543210',
            'id_type': 'Aadhar',
            'id_number': '12345678',
            'check_in_date': '2025-11-01',
            'govt_id_photo': test_image,
        }
        
        response = self.client.post(reverse('add_guest'), data)
        self.assertEqual(response.status_code, 200)
        resp = json.loads(response.content)
        self.assertTrue(resp.get('success'), f"Error: {resp.get('message')}")
        
        # Verify guest was created with image
        guest = Guest.objects.get(email='john@test.com')
        self.assertTrue(guest.govt_id_photo)
    
    def test_add_guest_with_college_id_photo(self):
        """Test adding guest with LPU ID photo"""
        
        test_image = SimpleUploadedFile(
            "college_id.png",
            b'fake png content',
            content_type="image/png"
        )
        
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'email': 'jane@test.com',
            'phone': '9876543211',
            'college_id': 'LP00123456',
            'check_in_date': '2025-11-01',
            'college_id_photo': test_image,
        }
        
        response = self.client.post(reverse('add_guest'), data)
        self.assertEqual(response.status_code, 200)
        resp = json.loads(response.content)
        self.assertTrue(resp.get('success'))
        
        guest = Guest.objects.get(email='jane@test.com')
        self.assertEqual(guest.college_id, 'LP00123456')
        self.assertTrue(guest.college_id_photo)
    
    def test_add_guest_with_document_verification(self):
        """Test adding guest with document verification image"""
        
        test_image = SimpleUploadedFile(
            "doc_verify.jpg",
            b'fake verification image',
            content_type="image/jpeg"
        )
        
        data = {
            'first_name': 'Bob',
            'last_name': 'Jones',
            'email': 'bob@test.com',
            'phone': '9876543212',
            'check_in_date': '2025-11-01',
            'document_verification_image': test_image,
        }
        
        response = self.client.post(reverse('add_guest'), data)
        self.assertEqual(response.status_code, 200)
        resp = json.loads(response.content)
        self.assertTrue(resp.get('success'))
        
        guest = Guest.objects.get(email='bob@test.com')
        self.assertTrue(guest.document_verification_image)
    
    def test_guest_with_all_document_images(self):
        """Test guest with all three document images"""
        
        id_image = SimpleUploadedFile("id.jpg", b'id image', content_type="image/jpeg")
        lpu_image = SimpleUploadedFile("lpu.png", b'lpu image', content_type="image/png")
        doc_image = SimpleUploadedFile("doc.jpg", b'doc image', content_type="image/jpeg")
        
        data = {
            'first_name': 'Alice',
            'last_name': 'Cooper',
            'email': 'alice@test.com',
            'phone': '9876543213',
            'id_type': 'Passport',
            'id_number': 'PASS123456',
            'college_id': 'LP00654321',
            'check_in_date': '2025-11-01',
            'govt_id_photo': id_image,
            'college_id_photo': lpu_image,
            'document_verification_image': doc_image,
        }
        
        response = self.client.post(reverse('add_guest'), data)
        self.assertEqual(response.status_code, 200)
        resp = json.loads(response.content)
        self.assertTrue(resp.get('success'), f"Error: {resp.get('message')}")
        
        guest = Guest.objects.get(email='alice@test.com')
        self.assertTrue(guest.govt_id_photo)
        self.assertTrue(guest.college_id_photo)
        self.assertTrue(guest.document_verification_image)
    
    def test_add_guest_with_invalid_file_extension(self):
        """Test that invalid file types are rejected"""
        
        # Try to upload a text file instead of image
        bad_file = SimpleUploadedFile(
            "not_image.txt",
            b'This is not an image',
            content_type="text/plain"
        )
        
        data = {
            'first_name': 'BadFile',
            'last_name': 'User',
            'email': 'badfile@test.com',
            'phone': '9876543214',
            'check_in_date': '2025-11-01',
            'govt_id_photo': bad_file,
        }
        
        response = self.client.post(reverse('add_guest'), data)
        self.assertEqual(response.status_code, 400)
        resp = json.loads(response.content)
        self.assertFalse(resp.get('success'))
        self.assertIn('image type', resp.get('message', '').lower())
    
    def test_update_guest_with_new_image(self):
        """Test updating guest with new image"""
        
        # Create initial guest
        guest = Guest.objects.create(
            first_name='Update',
            last_name='Test',
            email='update@test.com',
            phone='9876543215'
        )
        
        # Update with new image
        new_image = SimpleUploadedFile(
            "updated_id.jpg",
            b'updated image content',
            content_type="image/jpeg"
        )
        
        data = {
            'first_name': 'Updated',
            'last_name': 'Guest',
            'phone': '9876543215',
            'govt_id_photo': new_image,
        }
        
        response = self.client.post(reverse('update_guest', args=[guest.id]), data)
        self.assertEqual(response.status_code, 200)
        resp = json.loads(response.content)
        self.assertTrue(resp.get('success'))
        
        # Verify update
        guest.refresh_from_db()
        self.assertEqual(guest.first_name, 'Updated')
        self.assertTrue(guest.govt_id_photo)
