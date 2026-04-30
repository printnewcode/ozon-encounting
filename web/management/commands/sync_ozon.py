from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from web.services.ozon_sync import OzonSyncService


class Command(BaseCommand):
    help = 'Sync products, stocks and sales from Ozon Seller API.'

    def add_arguments(self, parser):
        parser.add_argument('--date-from', dest='date_from')
        parser.add_argument('--date-to', dest='date_to')

    def handle(self, *args, **options):
        date_to = timezone.localdate()
        date_from = date_to - timedelta(days=30)

        if options['date_from']:
            date_from = datetime.fromisoformat(options['date_from']).date()
        if options['date_to']:
            date_to = datetime.fromisoformat(options['date_to']).date()

        result = OzonSyncService().sync_all(date_from, date_to)

        self.stdout.write(self.style.SUCCESS(
            'Ozon sync completed: '
            f'products created={result.products_created}, '
            f'products updated={result.products_updated}, '
            f'stocks updated={result.stocks_updated}, '
            f'sales created={result.sales_created}, '
            f'sales skipped={result.sales_skipped}.'
        ))
