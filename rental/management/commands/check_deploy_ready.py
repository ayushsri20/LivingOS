from django.core.management.base import BaseCommand
from django.conf import settings
import os
import sys


class Command(BaseCommand):
    help = 'Checks common production settings to ensure safe deployment and data safety.'

    def handle(self, *args, **options):
        problems = []

        # SECRET_KEY
        if not os.environ.get('SECRET_KEY'):
            problems.append('SECRET_KEY is not set in environment; using an ephemeral key can invalidate sessions.')

        # DEBUG
        if settings.DEBUG:
            problems.append('DEBUG is True. Set DEBUG=False in production.')

        # ALLOWED_HOSTS
        ah = getattr(settings, 'ALLOWED_HOSTS', [])
        if not ah or all(h in ('localhost', '127.0.0.1') for h in ah):
            problems.append('ALLOWED_HOSTS looks like a development default; configure your production hosts.')

        # Database
        engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
        if 'sqlite' in engine:
            problems.append('SQLite is in use. SQLite is not recommended for production (concurrency, backups).')

        # Static root
        static_root = getattr(settings, 'STATIC_ROOT', None)
        if not static_root:
            problems.append('STATIC_ROOT is not configured.')

        # Media storage
        default_storage = getattr(settings, 'DEFAULT_FILE_STORAGE', 'local')
        if default_storage == 'local' and not os.environ.get('AWS_S3_BUCKET_NAME'):
            # local media is ok for single-instance but warn
            problems.append('Using local MEDIA storage. For multiple instances use S3 or shared volume.')

        # Report
        if problems:
            self.stdout.write(self.style.ERROR('Deployment checks found potential issues:'))
            for p in problems:
                self.stdout.write(self.style.WARNING(f'- {p}'))
            self.stdout.write('Fix the above before deploying to production. Use --force if you understand the risks.')
            sys.exit(2)

        self.stdout.write(self.style.SUCCESS('All basic deployment checks passed.'))
