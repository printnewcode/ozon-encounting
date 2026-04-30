from dataclasses import dataclass
from datetime import date, datetime, time, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from ..models import Product, SaleRecord
from .ozon_client import OzonSellerClient


@dataclass
class OzonSyncResult:
    products_created: int = 0
    products_updated: int = 0
    stocks_updated: int = 0
    sales_created: int = 0
    sales_skipped: int = 0


BLOCKING_STATUS_MARKERS = (
    'archived',
    'archive',
    'blocked',
    'disabled',
    'failed',
    'fail',
    'moderation_failed',
    'validation_failed',
    'rejected',
    'declined',
    'error',
)


def chunked(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def parse_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or '0')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def parse_ozon_date(value: str | None) -> date:
    if not value:
        return timezone.localdate()

    normalized = value.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return timezone.localdate()


def as_ozon_datetime(value: date, end_of_day: bool = False) -> str:
    moment = time.max if end_of_day else time.min
    return datetime.combine(value, moment, tzinfo=datetime_timezone.utc).isoformat().replace('+00:00', 'Z')


def item_offer_id(item: dict) -> str:
    return str(item.get('offer_id') or item.get('offer') or '').strip()


def item_product_id(item: dict):
    value = item.get('id') or item.get('product_id')
    return value or None


def item_sku(item: dict):
    sources = [
        item.get('sku'),
        item.get('fbo_sku'),
        item.get('fbs_sku'),
    ]
    for value in sources:
        if value:
            return value
    return None


def item_visibility(item: dict) -> str:
    return str(item.get('visibility') or item.get('visible') or '').strip()


def extract_status_values(value) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, dict):
        values = []
        for nested_value in value.values():
            values.extend(extract_status_values(nested_value))
        return values
    if isinstance(value, list):
        values = []
        for nested_value in value:
            values.extend(extract_status_values(nested_value))
        return values
    return [str(value).strip()]


def item_ozon_status(item: dict) -> str:
    statuses = extract_status_values(item.get('statuses') or item.get('status') or item.get('state'))
    return ', '.join(dict.fromkeys(value for value in statuses if value))[:100]


def has_blocking_status(item: dict) -> bool:
    status_text = item_ozon_status(item).lower()
    return any(marker in status_text for marker in BLOCKING_STATUS_MARKERS)


def stock_quantity(item: dict) -> int:
    total = 0
    stocks = item.get('stocks') or []

    if isinstance(stocks, dict):
        for stock in stocks.values():
            if isinstance(stock, dict):
                total += int(stock.get('present') or stock.get('quantity') or 0)
        return total

    for stock in stocks:
        total += int(stock.get('present') or stock.get('quantity') or 0)
    return total


def posting_date(posting: dict) -> date:
    for field in ('in_process_at', 'shipment_date', 'delivering_date', 'created_at'):
        if posting.get(field):
            return parse_ozon_date(posting[field])
    return timezone.localdate()


def posting_product_price(product: dict) -> Decimal:
    price = product.get('price')
    if price not in (None, ''):
        return parse_decimal(price)

    actions = product.get('actions') or []
    if actions:
        return parse_decimal(actions[0].get('price'))

    return Decimal('0.00')


def product_defaults(item: dict) -> dict:
    name = item.get('name') or item_offer_id(item)
    return {
        'name': name,
        'purchase_price': Decimal('0.00'),
        'delivery_cost': Decimal('0.00'),
        'quantity': 0,
        'status': 'in_stock',
        'ozon_product_id': item_product_id(item),
        'ozon_sku': item_sku(item),
        'ozon_visibility': item_visibility(item),
        'ozon_status': item_ozon_status(item),
    }


def update_product_from_ozon(product: Product, item: dict) -> bool:
    changed = False

    for field, value in (
        ('name', item.get('name') or product.name),
        ('ozon_product_id', item_product_id(item)),
        ('ozon_sku', item_sku(item)),
        ('ozon_visibility', item_visibility(item)),
        ('ozon_status', item_ozon_status(item)),
    ):
        if value not in (None, '') and getattr(product, field) != value:
            setattr(product, field, value)
            changed = True

    if changed:
        product.save()

    return changed


def is_product_sellable(product: Product, quantity: int) -> bool:
    return (
        quantity > 0
        and product.ozon_visibility == 'VISIBLE'
        and not any(marker in product.ozon_status.lower() for marker in BLOCKING_STATUS_MARKERS)
    )


def product_status_from_ozon(product: Product, quantity: int) -> str:
    if is_product_sellable(product, quantity):
        return 'in_sale'
    if quantity == 0 and product.sales.exists():
        return 'sold'
    return 'in_stock'


class OzonSyncService:
    def __init__(self, client: OzonSellerClient | None = None) -> None:
        self.client = client or OzonSellerClient()

    @transaction.atomic
    def sync_products(self) -> OzonSyncResult:
        result = OzonSyncResult()
        product_items = list(self.client.product_list())
        offer_ids = [item_offer_id(item) for item in product_items if item_offer_id(item)]

        details_by_offer_id = {}
        for offer_id_group in chunked(offer_ids, 1000):
            for item in self.client.product_info_list(offer_id_group):
                offer_id = item_offer_id(item)
                if offer_id:
                    details_by_offer_id[offer_id] = item

        for item in product_items:
            offer_id = item_offer_id(item)
            if not offer_id:
                continue

            detail = {**item, **details_by_offer_id.get(offer_id, {})}
            product, created = Product.objects.get_or_create(
                article=offer_id,
                defaults=product_defaults(detail),
            )
            if created:
                result.products_created += 1
            elif update_product_from_ozon(product, detail):
                result.products_updated += 1

        return result

    @transaction.atomic
    def sync_stocks(self) -> OzonSyncResult:
        result = OzonSyncResult()

        for item in self.client.product_stocks():
            offer_id = item_offer_id(item)
            if not offer_id:
                continue

            product, _ = Product.objects.get_or_create(
                article=offer_id,
                defaults=product_defaults(item),
            )
            quantity = stock_quantity(item)
            update_product_from_ozon(product, item)
            status = product_status_from_ozon(product, quantity)

            if product.quantity != quantity or product.status != status:
                product.quantity = quantity
                product.status = status
                product.save()
                result.stocks_updated += 1

        return result

    @transaction.atomic
    def sync_postings(self, date_from: date, date_to: date) -> OzonSyncResult:
        result = OzonSyncResult()
        date_from_value = as_ozon_datetime(date_from)
        date_to_value = as_ozon_datetime(date_to, end_of_day=True)

        for posting in self.client.fbo_postings(date_from_value, date_to_value):
            self.create_sales_from_posting(posting, 'fbo', result)

        for posting in self.client.fbs_postings(date_from_value, date_to_value):
            self.create_sales_from_posting(posting, 'fbs', result)

        return result

    def create_sales_from_posting(self, posting: dict, schema: str, result: OzonSyncResult) -> None:
        posting_number = posting.get('posting_number') or posting.get('order_number') or ''
        sale_date = posting_date(posting)

        for item_index, item in enumerate(posting.get('products') or []):
            offer_id = item_offer_id(item)
            if not offer_id:
                continue

            quantity = int(item.get('quantity') or 1)
            price = posting_product_price(item)
            product, _ = Product.objects.get_or_create(
                article=offer_id,
                defaults=product_defaults(item),
            )

            for unit_index in range(quantity):
                external_id = f'ozon:{schema}:{posting_number}:{item_index}:{unit_index}'
                if SaleRecord.objects.filter(external_id=external_id).exists():
                    result.sales_skipped += 1
                    continue

                SaleRecord.objects.create(
                    product=product,
                    sale_type='ozon',
                    income=price,
                    sale_date=sale_date,
                    external_id=external_id,
                    posting_number=posting_number,
                )
                result.sales_created += 1

    def sync_all(self, date_from: date, date_to: date) -> OzonSyncResult:
        total = OzonSyncResult()

        for result in (
            self.sync_products(),
            self.sync_stocks(),
            self.sync_postings(date_from, date_to),
        ):
            total.products_created += result.products_created
            total.products_updated += result.products_updated
            total.stocks_updated += result.stocks_updated
            total.sales_created += result.sales_created
            total.sales_skipped += result.sales_skipped

        return total
