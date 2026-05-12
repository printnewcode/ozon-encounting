from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
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
    sales_updated: int = 0


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

OZON_SERVICE_LABELS = {
    'MarketplaceServiceItemDirectFlowLogistic': 'Логистика до покупателя',
    'MarketplaceServiceItemDirectFlowTrans': 'Магистральная доставка',
    'MarketplaceServiceItemDirectFlowDelivToCustomer': 'Доставка покупателю',
    'MarketplaceServiceItemDirectFlowDeliveryToCustomer': 'Доставка покупателю',
    'MarketplaceServiceItemDeliveryToHandoverPlaceOzon': 'Доставка до места передачи OZON',
    'MarketplaceServiceItemDropoffFF': 'Обработка отправления',
    'MarketplaceServiceItemDropoffPVZ': 'Прием в пункте приема',
    'MarketplaceServiceItemDropoffSC': 'Прием в сортировочном центре',
    'MarketplaceServiceItemFulfillment': 'Сборка и обработка отправления',
    'MarketplaceServiceItemPickup': 'Забор отправления',
    'MarketplaceServiceItemReturnAfterDelivToCustomer': 'Возврат после доставки',
    'MarketplaceServiceItemReturnFlowLogistic': 'Логистика возврата',
    'MarketplaceServiceItemReturnFlowTrans': 'Магистраль возврата',
    'MarketplaceServiceItemReturnNotDelivToCustomer': 'Возврат недоставленного товара',
    'MarketplaceServiceItemRedistributionLastMileCourier': 'Последняя миля, курьер',
    'MarketplaceRedistributionOfAcquiringOperation': 'Эквайринг',
    'MarketplaceServiceItemRedistributionReturnsPVZ': 'Обработка возврата в ПВЗ',
    'MarketplaceServiceItemRedistributionReturnsCourier': 'Обработка возврата курьером',
    'MarketplaceServiceItemRedistributionReturnsSC': 'Обработка возврата в сортировочном центре',
    'MarketplaceServiceItemRedistributionLastMilePVZ': 'Последняя миля, ПВЗ',
    'MarketplaceServiceItemRedistributionLastMileSC': 'Последняя миля, сортировочный центр',
    'MarketplaceServiceItemStorage': 'Хранение',
    'MarketplaceServiceItemUtilization': 'Утилизация',
    'MarketplaceServiceItemServiceFee': 'Комиссия OZON',
}

OZON_OPERATION_LABELS = {
    'OperationAgentDeliveredToCustomer': 'Доставка покупателю',
    'OperationAgentStornoDeliveredToCustomer': 'Отмена доставки покупателю',
    'OperationMarketplaceServiceStorage': 'Хранение',
    'OperationMarketplaceServicePremiumCashback': 'Premium-кэшбэк',
    'ClientReturnAgentOperation': 'Возврат покупателя',
    'OperationMarketplaceCrossDockServiceWriteOff': 'Кросс-докинг',
    'MarketplaceMarketingActionCostOperation': 'Маркетинговая акция',
}


def chunked(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def chunked_date_range(date_from: date, date_to: date, max_days: int = 28):
    current = date_from
    while current <= date_to:
        chunk_to = min(current + timedelta(days=max_days - 1), date_to)
        yield current, chunk_to
        current = chunk_to + timedelta(days=1)


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


def item_key_values(item: dict) -> list[str]:
    values = [
        item_offer_id(item),
        item_sku(item),
        item.get('product_id'),
    ]
    return list(dict.fromkeys(str(value).strip() for value in values if value not in (None, '')))


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


def warehouse_stock_offer_id(item: dict) -> str:
    return str(
        item.get('item_code')
        or item.get('offer_id')
        or item.get('offer')
        or ''
    ).strip()


def warehouse_stock_quantity(item: dict) -> int:
    for field in ('free_to_sell_amount', 'present', 'quantity', 'available_stock_count', 'valid_stock_count'):
        if item.get(field) not in (None, ''):
            return int(item.get(field) or 0)
    return 0


def stock_on_warehouses_quantities(items) -> dict[str, int]:
    quantities = defaultdict(int)
    for item in items:
        offer_id = warehouse_stock_offer_id(item)
        if offer_id:
            quantities[offer_id] += warehouse_stock_quantity(item)
    return dict(quantities)


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


def operation_posting_number(operation: dict) -> str:
    posting = operation.get('posting') or {}
    return str(
        posting.get('posting_number')
        or operation.get('posting_number')
        or operation.get('order_number')
        or ''
    ).strip()


def operation_item_weight(item: dict) -> Decimal:
    for field in ('accruals_for_sale', 'price', 'amount', 'payout'):
        value = item.get(field)
        if value not in (None, ''):
            return abs(parse_decimal(value))
    return Decimal('0.00')


def operation_item_net_amount(item: dict) -> Decimal:
    if item.get('amount') not in (None, ''):
        return parse_decimal(item.get('amount'))
    if item.get('payout') not in (None, ''):
        return parse_decimal(item.get('payout'))

    total = Decimal('0.00')
    for field in ('accruals_for_sale', 'sale_commission'):
        if item.get(field) not in (None, ''):
            total += parse_decimal(item.get(field))
    return total


@dataclass
class OzonFinanceEntry:
    amount: Decimal
    accrual_id: str = ''
    accrual_date: date | None = None
    operation_type: str = ''
    operation_name: str = ''
    services: list | None = None
    items: list | None = None


@dataclass
class OzonFinanceIndex:
    item_entries: dict
    posting_entries: dict

    def entry_for_item(self, posting_number: str, item: dict, posting_products_count: int) -> OzonFinanceEntry | None:
        posting_number = str(posting_number or '').strip()
        if not posting_number:
            return None

        for key in item_key_values(item):
            entry = self.item_entries.get((posting_number, key))
            if entry is not None:
                return entry

        if posting_products_count == 1:
            return self.posting_entries.get(posting_number)

        return None


def decimal_as_string(value) -> str:
    return str(parse_decimal(value))


def ozon_label(value: str, labels: dict[str, str]) -> str:
    value = str(value or '').strip()
    return labels.get(value, value)


def finance_services(operation: dict) -> list[dict]:
    services = []
    for service in operation.get('services') or []:
        raw_name = str(service.get('name') or service.get('service_name') or service.get('type') or '').strip()
        services.append({
            **service,
            'code': raw_name,
            'name': ozon_label(raw_name, OZON_SERVICE_LABELS) or 'Списание',
            'price': decimal_as_string(service.get('price')),
        })
    return services


def finance_items(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items:
        raw_operation_type = str(item.get('operation_type') or '').strip()
        normalized.append({
            **item,
            'sku': str(item.get('sku') or '').strip(),
            'offer_id': item_offer_id(item),
            'name': str(item.get('name') or '').strip(),
            'amount': decimal_as_string(item.get('amount')),
            'payout': decimal_as_string(item.get('payout')),
            'accruals_for_sale': decimal_as_string(item.get('accruals_for_sale')),
            'sale_commission': decimal_as_string(item.get('sale_commission')),
            'operation_type': raw_operation_type,
            'operation_type_name': ozon_label(raw_operation_type, OZON_OPERATION_LABELS),
        })
    return normalized


def add_finance_entry(
    entries: dict,
    key,
    amount: Decimal,
    operation: dict,
    services: list[dict],
    items: list[dict],
) -> None:
    accrual_id = str(operation.get('operation_id') or '').strip()
    accrual_date = parse_ozon_date(operation.get('operation_date')) if operation.get('operation_date') else None
    current = entries.get(key)
    if current is None:
        entries[key] = OzonFinanceEntry(
            amount=amount,
            accrual_id=accrual_id,
            accrual_date=accrual_date,
            operation_type=str(operation.get('operation_type') or '').strip(),
            operation_name=(
                str(operation.get('operation_type_name') or operation.get('operation_name') or '').strip()
                or ozon_label(str(operation.get('operation_type') or '').strip(), OZON_OPERATION_LABELS)
            ),
            services=list(services),
            items=list(items),
        )
        return

    current.amount += amount
    if not current.accrual_id and accrual_id:
        current.accrual_id = accrual_id
    if current.accrual_date is None and accrual_date is not None:
        current.accrual_date = accrual_date
    if not current.operation_type and operation.get('operation_type'):
        current.operation_type = str(operation.get('operation_type')).strip()
    if not current.operation_name and (operation.get('operation_type_name') or operation.get('operation_name')):
        current.operation_name = str(operation.get('operation_type_name') or operation.get('operation_name')).strip()
    current.services = (current.services or []) + list(services)
    current.items = (current.items or []) + list(items)


def build_finance_index(operations) -> OzonFinanceIndex:
    item_entries = {}
    posting_entries = {}

    for operation in operations:
        posting_number = operation_posting_number(operation)
        items = operation.get('items') or []
        if not posting_number or not items:
            continue

        services = finance_services(operation)
        normalized_items = finance_items(items)
        operation_amount = parse_decimal(operation.get('amount'))
        if operation_amount == Decimal('0.00'):
            operation_amount = sum((operation_item_net_amount(item) for item in items), Decimal('0.00'))

        if operation_amount == Decimal('0.00'):
            continue

        weights = [operation_item_weight(item) for item in items]
        total_weight = sum(weights, Decimal('0.00'))
        allocated = Decimal('0.00')

        for index, item in enumerate(items):
            keys = item_key_values(item)
            if not keys:
                continue

            if index == len(items) - 1:
                item_amount = operation_amount - allocated
            elif total_weight:
                item_amount = (operation_amount * weights[index] / total_weight).quantize(Decimal('0.01'))
                allocated += item_amount
            else:
                item_amount = (operation_amount / len(items)).quantize(Decimal('0.01'))
                allocated += item_amount

            for key in keys:
                add_finance_entry(item_entries, (posting_number, key), item_amount, operation, services, normalized_items)
            add_finance_entry(posting_entries, posting_number, item_amount, operation, services, normalized_items)

    return OzonFinanceIndex(item_entries, posting_entries)


def posting_product_net_income(
    product: dict,
    posting_number: str,
    quantity: int,
    finance_index: OzonFinanceIndex,
    posting_products_count: int,
) -> tuple[Decimal, OzonFinanceEntry | None]:
    entry = finance_index.entry_for_item(posting_number, product, posting_products_count)
    if entry is not None and quantity > 0:
        return (entry.amount / quantity).quantize(Decimal('0.01')), entry
    return posting_product_price(product), None


def sale_accrual_details(product: dict, income: Decimal, finance_entry: OzonFinanceEntry | None) -> dict:
    gross_price = posting_product_price(product)
    details = {
        'gross_price': str(gross_price),
        'net_income': str(income),
        'deductions_total': str((gross_price - income).quantize(Decimal('0.01'))),
        'services': [],
        'items': [],
    }
    if finance_entry is None:
        return details

    details.update({
        'operation_type': finance_entry.operation_type,
        'operation_name': finance_entry.operation_name,
        'services': finance_entry.services or [],
        'items': finance_entry.items or [],
    })
    return details


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
    visibility = product.ozon_visibility.lower()
    return (
        quantity > 0
        and visibility not in {'invisible', 'hidden'}
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
        warehouse_quantities = stock_on_warehouses_quantities(self.client.stock_on_warehouses())
        seen_offer_ids = set()

        for item in self.client.product_stocks():
            offer_id = item_offer_id(item)
            if not offer_id:
                continue
            seen_offer_ids.add(offer_id)

            product, _ = Product.objects.get_or_create(
                article=offer_id,
                defaults=product_defaults(item),
            )
            quantity = max(stock_quantity(item), warehouse_quantities.get(offer_id, 0))
            update_product_from_ozon(product, item)
            status = product_status_from_ozon(product, quantity)

            if product.quantity != quantity or product.status != status:
                product.quantity = quantity
                product.status = status
                product.save()
                result.stocks_updated += 1

        for offer_id, quantity in warehouse_quantities.items():
            if offer_id in seen_offer_ids:
                continue

            product, _ = Product.objects.get_or_create(
                article=offer_id,
                defaults=product_defaults({'offer_id': offer_id}),
            )
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

        for chunk_from, chunk_to in chunked_date_range(date_from, date_to):
            date_from_value = as_ozon_datetime(chunk_from)
            date_to_value = as_ozon_datetime(chunk_to, end_of_day=True)
            finance_index = build_finance_index(self.client.finance_transactions(date_from_value, date_to_value))

            for posting in self.client.fbo_postings(date_from_value, date_to_value):
                self.create_sales_from_posting(posting, 'fbo', result, finance_index)

            for posting in self.client.fbs_postings(date_from_value, date_to_value):
                self.create_sales_from_posting(posting, 'fbs', result, finance_index)

        return result

    def create_sales_from_posting(
        self,
        posting: dict,
        schema: str,
        result: OzonSyncResult,
        finance_index: OzonFinanceIndex,
    ) -> None:
        posting_number = posting.get('posting_number') or posting.get('order_number') or ''
        sale_date = posting_date(posting)
        products = posting.get('products') or []
        posting_products_count = len(products)

        for item_index, item in enumerate(products):
            offer_id = item_offer_id(item)
            if not offer_id:
                continue

            quantity = int(item.get('quantity') or 1)
            income, finance_entry = posting_product_net_income(
                item,
                posting_number,
                quantity,
                finance_index,
                posting_products_count,
            )
            accrual_details = sale_accrual_details(item, income, finance_entry)
            product, _ = Product.objects.get_or_create(
                article=offer_id,
                defaults=product_defaults(item),
            )

            for unit_index in range(quantity):
                external_id = f'ozon:{schema}:{posting_number}:{item_index}:{unit_index}'
                existing_sale = SaleRecord.objects.filter(external_id=external_id).first()
                if existing_sale:
                    accrual_id = finance_entry.accrual_id if finance_entry else None
                    accrual_date = finance_entry.accrual_date if finance_entry else None
                    if (
                        existing_sale.income != income
                        or existing_sale.accrual_id != accrual_id
                        or existing_sale.accrual_date != accrual_date
                        or existing_sale.accrual_details != accrual_details
                    ):
                        existing_sale.income = income
                        existing_sale.accrual_id = accrual_id
                        existing_sale.accrual_date = accrual_date
                        existing_sale.accrual_details = accrual_details
                        existing_sale.save()
                        result.sales_updated += 1
                    result.sales_skipped += 1
                    continue

                SaleRecord.objects.create(
                    product=product,
                    sale_type='ozon',
                    income=income,
                    sale_date=sale_date,
                    accrual_date=finance_entry.accrual_date if finance_entry else None,
                    accrual_id=finance_entry.accrual_id if finance_entry else None,
                    accrual_details=accrual_details,
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
            total.sales_updated += result.sales_updated

        return total
