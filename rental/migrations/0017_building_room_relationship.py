import django.db.models.deletion
from django.db import migrations, models


BUILDING_NAMES = ('M1', '1', '2', '3', '4', '5')
PREFIX_TO_BUILDING = {
    'A': 'M1',
    'B': '1',
    'C': '2',
    'D': '3',
    'E': '4',
    'F': '5',
}

FRESH_DATABASE_INVENTORY = (
    ('A-101', 'single', '7500.00', 'M1'),
    ('A-102', 'single', '7500.00', 'M1'),
    ('A-103', 'double', '8000.00', 'M1'),
    ('A-104', 'double', '8000.00', 'M1'),
    ('A-105', 'suite', '7000.00', 'M1'),
    ('A-106', 'single', '7000.00', 'M1'),
    ('B-101', 'single', '7000.00', '1'),
    ('B-102', 'single', '7000.00', '1'),
    ('B-103', 'double', '7000.00', '1'),
    ('B-104', 'double', '7000.00', '1'),
    ('B-105', 'single', '7000.00', '1'),
    ('B-106', 'single', '7000.00', '1'),
    ('C-101', 'single', '7000.00', '2'),
    ('C-102', 'single', '7000.00', '2'),
    ('C-103', 'double', '7000.00', '2'),
    ('C-104', 'double', '7000.00', '2'),
    ('C-105', 'single', '7000.00', '2'),
    ('C-106', 'suite', '7000.00', '2'),
    ('D-101', 'single', '7000.00', '3'),
    ('D-102', 'single', '7000.00', '3'),
    ('D-103', 'double', '7000.00', '3'),
    ('D-104', 'double', '7000.00', '3'),
    ('D-105', 'single', '7000.00', '3'),
    ('D-106', 'single', '7000.00', '3'),
    ('E-101', 'single', '7000.00', '4'),
    ('E-102', 'single', '7000.00', '4'),
    ('E-103', 'double', '7000.00', '4'),
    ('E-104', 'double', '7000.00', '4'),
    ('E-105', 'single', '7000.00', '4'),
    ('E-106', 'single', '7000.00', '4'),
    ('F-101', 'single', '7000.00', '5'),
    ('F-102', 'single', '7000.00', '5'),
    ('F-103', 'double', '7000.00', '5'),
    ('F-104', 'double', '7000.00', '5'),
    ('F-105', 'single', '7000.00', '5'),
    ('F-106', 'single', '7000.00', '5'),
)


def assign_existing_rooms(apps, schema_editor):
    Building = apps.get_model('rental', 'Building')
    Room = apps.get_model('rental', 'Room')
    database = schema_editor.connection.alias

    rooms = list(Room.objects.using(database).only('id', 'number').order_by('id'))
    if Building.objects.using(database).exists():
        raise RuntimeError('The new Building table is not empty; refusing to alter existing buildings.')

    fresh_database = not rooms
    if fresh_database:
        for model_name in ('Booking', 'Guest', 'MonthlyPayment', 'ElectricityBill', 'PaymentRecord'):
            RelatedModel = apps.get_model('rental', model_name)
            if RelatedModel.objects.using(database).exists():
                raise RuntimeError(
                    f'Cannot bootstrap room inventory: {model_name} records exist without rooms.'
                )

        expected_inventory = [
            (number, building_name)
            for number, _room_type, _price, building_name in FRESH_DATABASE_INVENTORY
        ]
        if (
            len(FRESH_DATABASE_INVENTORY) != 36
            or len({number for number, _building_name in expected_inventory}) != 36
            or any(
                PREFIX_TO_BUILDING.get(number.split('-', 1)[0]) != building_name
                for number, building_name in expected_inventory
            )
            or {building_name for _number, building_name in expected_inventory} != set(BUILDING_NAMES)
            or any(
                sum(building_name == name for _number, building_name in expected_inventory) != 6
                for name in BUILDING_NAMES
            )
        ):
            raise RuntimeError('The explicit fresh-database room inventory failed validation.')
    else:
        if len(rooms) != 36:
            raise RuntimeError(f'Expected exactly 36 existing rooms, found {len(rooms)}.')
        if len({room.id for room in rooms}) != len(rooms):
            raise RuntimeError('Duplicate room IDs found; refusing to assign buildings.')
        if len({room.number for room in rooms}) != len(rooms):
            raise RuntimeError('Duplicate room numbers found; refusing to assign buildings.')

    Building.objects.using(database).bulk_create([
        Building(name=name) for name in BUILDING_NAMES
    ])
    buildings = {
        building.name: building
        for building in Building.objects.using(database).all()
    }
    if set(buildings) != set(BUILDING_NAMES) or len(buildings) != 6:
        raise RuntimeError('Building creation did not produce exactly the six required unique names.')

    if fresh_database:
        Room.objects.using(database).bulk_create([
            Room(
                number=number,
                room_type=room_type,
                price=price,
                agreed_rent=price,
                capacity=2,
                is_available=True,
                building=buildings[building_name],
            )
            for number, room_type, price, building_name in FRESH_DATABASE_INVENTORY
        ])
        rooms = list(Room.objects.using(database).only('id', 'number').order_by('id'))
        if len(rooms) != 36 or len({room.number for room in rooms}) != 36:
            raise RuntimeError('Fresh-database inventory creation did not produce 36 unique rooms.')

    if len(rooms) != 36:
        raise RuntimeError(f'Expected exactly 36 rooms after inventory setup, found {len(rooms)}.')
    if len({room.id for room in rooms}) != len(rooms):
        raise RuntimeError('Duplicate room IDs found; refusing to assign buildings.')
    if len({room.number for room in rooms}) != len(rooms):
        raise RuntimeError('Duplicate room numbers found; refusing to assign buildings.')

    grouped_room_ids = {name: [] for name in BUILDING_NAMES}
    for room in rooms:
        prefix = room.number.split('-', 1)[0] if '-' in room.number else ''
        building_name = PREFIX_TO_BUILDING.get(prefix)
        if building_name is None:
            raise RuntimeError(f'Unknown building prefix for existing room {room.number!r}.')
        grouped_room_ids[building_name].append(room.id)

    invalid_counts = {
        name: len(room_ids)
        for name, room_ids in grouped_room_ids.items()
        if len(room_ids) != 6
    }
    if invalid_counts:
        raise RuntimeError(f'Expected exactly six rooms per building; found {invalid_counts}.')
    if set(grouped_room_ids) != set(BUILDING_NAMES):
        raise RuntimeError('Rooms do not map to all six required buildings.')

    assigned_ids = []
    for name, room_ids in grouped_room_ids.items():
        building_id = buildings[name].pk
        for room_id in room_ids:
            changed = Room.objects.using(database).filter(pk=room_id).update(building_id=building_id)
            if changed != 1:
                raise RuntimeError(f'Expected to map room ID {room_id} exactly once; updated {changed} rows.')
            assigned_ids.append(room_id)

    if len(assigned_ids) != len(set(assigned_ids)) or set(assigned_ids) != {room.id for room in rooms}:
        raise RuntimeError('Not every existing room was assigned to exactly one building.')
    if Room.objects.using(database).filter(building__isnull=True).exists():
        raise RuntimeError('At least one existing room remains without a building.')
    if Building.objects.using(database).count() != 6:
        raise RuntimeError('Expected exactly six Building records after assignment.')
    for name, room_ids in grouped_room_ids.items():
        if Room.objects.using(database).filter(building__name=name).count() != len(room_ids):
            raise RuntimeError(f'Post-assignment room count validation failed for building {name}.')

    final_room_identity = list(
        Room.objects.using(database).order_by('id').values_list('id', 'number')
    )
    if final_room_identity != [(room.id, room.number) for room in rooms]:
        raise RuntimeError('Room IDs or numbers changed during building assignment.')


def unassign_existing_rooms(apps, schema_editor):
    Building = apps.get_model('rental', 'Building')
    Room = apps.get_model('rental', 'Room')
    database = schema_editor.connection.alias
    Room.objects.using(database).update(building=None)
    Building.objects.using(database).filter(name__in=BUILDING_NAMES).delete()


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ('rental', '0016_seed_required_room_inventory'),
    ]

    operations = [
        migrations.CreateModel(
            name='Building',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=30, unique=True)),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.AddField(
            model_name='room',
            name='building',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rooms',
                to='rental.building',
            ),
        ),
        migrations.RunPython(assign_existing_rooms, unassign_existing_rooms),
        migrations.AlterField(
            model_name='room',
            name='building',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rooms',
                to='rental.building',
            ),
        ),
    ]
