from django.db import migrations

# Role groups the app checks by name (see is_inventory_or_admin / is_hr_or_admin).
ROLE_GROUPS = ['Inventory', 'HR']


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('inventory', '0003_alter_fabric_unit_price_and_more'),
    ]

    operations = [
        migrations.RunPython(create_groups, migrations.RunPython.noop),
    ]
