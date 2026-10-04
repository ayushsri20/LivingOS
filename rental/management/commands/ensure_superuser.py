"""
Idempotent production superuser bootstrap.

Render's free plan offers neither a Shell nor a Pre-Deploy command, so the only
hook available is the build step. This command is invoked from build.sh and is
safe to run on every deploy.

It never hardcodes or prints a credential: everything comes from the
DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD environment variables.

Behaviour:
  * any variable missing  -> skip, succeed (local and CI builds stay unaffected)
  * username absent       -> create the superuser
  * username exists and is a superuser -> no-op, succeed
  * username exists but is not a superuser -> raise CommandError, which fails
    the build. The existing account is never modified, re-flagged or deleted.
  * database errors       -> propagate, never swallowed
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

ENV_USERNAME = 'DJANGO_SUPERUSER_USERNAME'
ENV_EMAIL = 'DJANGO_SUPERUSER_EMAIL'
ENV_PASSWORD = 'DJANGO_SUPERUSER_PASSWORD'


class Command(BaseCommand):
    help = 'Creates the production superuser from DJANGO_SUPERUSER_* env vars, if provided.'

    def handle(self, *args, **options):
        username = os.environ.get(ENV_USERNAME, '').strip()
        email = os.environ.get(ENV_EMAIL, '').strip()
        password = os.environ.get(ENV_PASSWORD, '')

        missing = [
            name
            for name, value in (
                (ENV_USERNAME, username),
                (ENV_EMAIL, email),
                (ENV_PASSWORD, password),
            )
            if not value
        ]

        if missing:
            self.stdout.write(
                'DJANGO_SUPERUSER_* variables not set; skipping superuser bootstrap.'
            )
            return

        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD

        # create_superuser() is Django's own manager API, so password hashing
        # and defaults match `manage.py createsuperuser` exactly.
        existing = user_model._default_manager.filter(**{username_field: username}).first()

        if existing is None:
            user_model._default_manager.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(
                self.style.SUCCESS(f'Created superuser "{username}".')
            )
            return

        if existing.is_superuser:
            # Already provisioned by an earlier deploy: leave it completely
            # alone, including its password.
            self.stdout.write(
                f'Superuser "{username}" already exists; leaving it unchanged.'
            )
            return

        # Refuse rather than promote or overwrite somebody's account.
        raise CommandError(
            f'User "{username}" already exists but is not a superuser. '
            'Refusing to modify an existing account. Choose a different '
            f'{ENV_USERNAME} or remove the conflicting user manually.'
        )