import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class OzonAPIError(Exception):
    pass


class OzonSellerClient:
    base_url = 'https://api-seller.ozon.ru'

    def __init__(self, client_id: str | None = None, api_key: str | None = None) -> None:
        self.client_id = client_id if client_id is not None else settings.OZON_CLIENT_ID
        self.api_key = api_key if api_key is not None else settings.OZON_API_KEY

        if not self.client_id or not self.api_key:
            raise OzonAPIError('Ozon API credentials are not configured.')

    def post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode('utf-8')
        request = Request(
            f'{self.base_url}{path}',
            data=body,
            headers={
                'Client-Id': self.client_id,
                'Api-Key': self.api_key,
                'Content-Type': 'application/json',
            },
            method='POST',
        )

        for attempt in range(3):
            try:
                with urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode('utf-8'))
            except HTTPError as exc:
                error_body = exc.read().decode('utf-8', errors='replace')
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise OzonAPIError(f'Ozon API error {exc.code}: {error_body}') from exc
            except URLError as exc:
                raise OzonAPIError(f'Ozon API connection error: {exc.reason}') from exc

        raise OzonAPIError('Ozon API request failed.')

    def product_list(self, visibility: str = 'ALL', limit: int = 1000):
        last_id = ''

        while True:
            data = self.post('/v3/product/list', {
                'filter': {
                    'visibility': visibility,
                },
                'last_id': last_id,
                'limit': limit,
            })
            result = data.get('result', {})
            items = result.get('items', [])
            yield from items

            last_id = result.get('last_id') or ''
            if not last_id or len(items) < limit:
                break

    def product_info_list(self, offer_ids: list[str]) -> list[dict]:
        if not offer_ids:
            return []

        data = self.post('/v3/product/info/list', {
            'offer_id': offer_ids,
            'product_id': [],
            'sku': [],
        })
        return data.get('items') or data.get('result', {}).get('items', [])

    def product_stocks(self, visibility: str = 'ALL', limit: int = 1000):
        cursor = ''

        while True:
            data = self.post('/v4/product/info/stocks', {
                'cursor': cursor,
                'filter': {
                    'visibility': visibility,
                },
                'limit': limit,
            })
            result = data.get('result') or data
            items = result.get('items', [])
            yield from items

            cursor = result.get('cursor') or ''
            if not cursor or len(items) < limit:
                break

    def fbo_postings(self, date_from: str, date_to: str, limit: int = 1000):
        offset = 0

        while True:
            data = self.post('/v2/posting/fbo/list', {
                'dir': 'ASC',
                'filter': {
                    'since': date_from,
                    'to': date_to,
                },
                'limit': limit,
                'offset': offset,
                'translit': False,
                'with': {
                    'analytics_data': False,
                    'financial_data': True,
                },
            })
            postings = data.get('result', [])
            yield from postings

            if len(postings) < limit:
                break
            offset += limit

    def fbs_postings(self, date_from: str, date_to: str, limit: int = 1000):
        offset = 0

        while True:
            data = self.post('/v3/posting/fbs/list', {
                'dir': 'ASC',
                'filter': {
                    'since': date_from,
                    'to': date_to,
                },
                'limit': limit,
                'offset': offset,
                'with': {
                    'analytics_data': False,
                    'barcodes': False,
                    'financial_data': True,
                    'translit': False,
                },
            })
            result = data.get('result', {})
            postings = result.get('postings', [])
            yield from postings

            if len(postings) < limit:
                break
            offset += limit

    def finance_transactions(self, date_from: str, date_to: str, page_size: int = 1000):
        page = 1

        while True:
            data = self.post('/v3/finance/transaction/list', {
                'filter': {
                    'date': {
                        'from': date_from,
                        'to': date_to,
                    },
                    'operation_type': [],
                    'posting_number': '',
                    'transaction_type': 'all',
                },
                'page': page,
                'page_size': page_size,
            })
            result = data.get('result', {})
            operations = result.get('operations', [])
            yield from operations

            page_count = int(result.get('page_count') or 0)
            if not operations or (page_count and page >= page_count) or len(operations) < page_size:
                break
            page += 1
