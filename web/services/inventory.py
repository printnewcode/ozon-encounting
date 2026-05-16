from decimal import Decimal

from django.db.models import Sum

from web.models import Product, SupplyBatch


def create_supply_batch(
    product: Product,
    quantity: int,
    purchase_price: Decimal,
    delivery_cost: Decimal,
) -> SupplyBatch:
    return SupplyBatch.objects.create(
        product=product,
        initial_quantity=quantity,
        remaining_quantity=quantity,
        cost_remaining_quantity=quantity,
        purchase_price=purchase_price,
        delivery_cost=delivery_cost,
    )


def product_warehouse_quantity(product: Product) -> int:
    quantity = product.batches.aggregate(total=Sum('remaining_quantity'))['total']
    if quantity is None:
        return max(product.quantity, 0)
    return max(int(quantity), 0)


def sync_product_warehouse_quantity(product: Product) -> None:
    product.quantity = product_warehouse_quantity(product)
    if product.quantity > 0:
        product.status = 'in_stock_warehouse'
    elif product.ozon_quantity > 0:
        product.status = 'in_sale' if product.status == 'in_sale' else 'in_stock_ozon'
    else:
        product.status = 'sold'
    product.save()


def allocate_unit_cost(product: Product, consume_warehouse: bool) -> tuple[SupplyBatch | None, Decimal]:
    batch = (
        product.batches.select_for_update()
        .filter(cost_remaining_quantity__gt=0)
        .order_by('created_at', 'id')
        .first()
    )
    if batch is None:
        return None, product.cost_price

    batch.cost_remaining_quantity = max(batch.cost_remaining_quantity - 1, 0)
    if consume_warehouse and batch.remaining_quantity > 0:
        batch.remaining_quantity -= 1
    batch.save(update_fields=['remaining_quantity', 'cost_remaining_quantity'])
    return batch, batch.cost_price
