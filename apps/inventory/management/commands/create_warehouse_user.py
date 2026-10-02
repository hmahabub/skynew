"""
Create (or update) a warehouse-only user: a member of the "Inventory" group
who can use Warehouse Management but not HR, Accounts, Django admin or the
admin-only parts of the warehouse (unit prices, approvals).

Usage:
    python manage.py create_warehouse_user <username>

You'll be asked for the password, so it never ends up in shell history.
Running it again for an existing user resets their password and makes sure
they're warehouse-only.
"""
import getpass

from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

WAREHOUSE_GROUP = 'Inventory'


class Command(BaseCommand):
    help = "Create a user who can only use Warehouse Management."

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--first-name', default='')
        parser.add_argument('--last-name', default='')

    def handle(self, *args, username, first_name, last_name, **options):
        password = getpass.getpass(f"Password for {username}: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("Passwords didn't match.")

        user = User.objects.filter(username=username).first() or User(username=username)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))

        created = user.pk is None
        user.first_name = first_name or user.first_name
        user.last_name = last_name or user.last_name
        # Warehouse-only: no Django admin, no superuser powers.
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        user.set_password(password)
        user.save()

        group, _ = Group.objects.get_or_create(name=WAREHOUSE_GROUP)
        user.groups.set([group])

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f'{verb} warehouse user "{username}". They can log in and use Warehouse Management only.'
        ))
