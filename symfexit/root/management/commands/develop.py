from argparse import ArgumentParser
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = 'Setup symfexit development environment.'

    def add_arguments(self, parser: ArgumentParser):
        subparsers = parser.add_subparsers(dest='command', help='Sub-commands.')
        superuser_parser = subparsers.add_parser('superuser', help='Create superuser.')
        superuser_parser.add_argument('username', type=str, help='Username of the superuser.')
        superuser_parser.add_argument('email', type=str, help='Email of the superuser.')
        return super().add_arguments(parser)

    def handle(self, *args, **options):
        if options['command'] == 'superuser':
            print('Creating superuser...')
        else:
            print('Setting up development environment...')
