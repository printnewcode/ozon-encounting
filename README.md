# ozon-encounting

Внутренний Django-сервис для учета товаров, поставок, остатков и продаж через OZON и свободные продажи. Приложение умеет импортировать Excel/CSV-файлы, синхронизироваться с OZON API, вести FIFO-себестоимость партий и формировать XLSX-отчеты по продажам и остаткам.

## Возможности

- загрузка поставок из Excel/CSV;
- загрузка свободных продаж и OZON-продаж из Excel/CSV;
- синхронизация товаров, остатков, отправлений и финансовых начислений OZON;
- раздельный учет остатков на складе и на OZON;
- FIFO-расчет себестоимости на момент продажи;
- расчет прибыли с учетом расходов OZON;
- экспорт отчета продаж и отчета остатков в XLSX;
- страница статистики по продажам и остаткам.

## Технологии

- Python 3
- Django
- SQLite для локальной разработки
- MySQL или PostgreSQL для альтернативного окружения
- pandas и openpyxl для импорта и экспорта таблиц
- OZON Seller API

## Быстрый старт

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

После запуска приложение доступно по адресу:

```text
http://127.0.0.1:8000/
```

Если PowerShell запрещает запуск скриптов активации, можно использовать Python из venv напрямую:

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

## Настройка окружения

Основные настройки берутся из `.env`. Для локального запуска достаточно скопировать `.env.example`.

```env
DEBUG=True
LOCAL=True
SECRET_KEY=
ALLOWED_HOSTS=127.0.0.1,localhost
DB_ENGINE=sqlite
SQLITE_PATH=
OZON_CLIENT_ID=
OZON_API_KEY=
```

В production обязательно задайте:

- `DEBUG=False`
- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `STATIC_ROOT`
- `OZON_CLIENT_ID`
- `OZON_API_KEY`

Для SQLite можно оставить `DB_ENGINE=sqlite`. Для MySQL или PostgreSQL задайте:

```env
DB_ENGINE=mysql
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=3306
```

или:

```env
DB_ENGINE=postgres
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
```

## Команды разработки

Применить миграции:

```powershell
.\venv\Scripts\python.exe manage.py migrate
```

Создать администратора:

```powershell
.\venv\Scripts\python.exe manage.py createsuperuser
```

Запустить сервер:

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

Запустить тесты:

```powershell
.\venv\Scripts\python.exe manage.py test web
```

Синхронизировать OZON из командной строки:

```powershell
.\venv\Scripts\python.exe manage.py sync_ozon
```

## Основные страницы

- `/products/` - список товаров, остатков и продаж;
- `/upload/supply/` - загрузка поставки;
- `/upload/sales/` - загрузка продаж;
- `/statistics/` - статистика;
- `/reports/sales/` - выбор периода отчета продаж;
- `/exports/sales-report/` - экспорт отчета продаж;
- `/exports/stock-balance/` - экспорт отчета остатков.

## Форматы импорта

### Поставка

Минимальные колонки:

```text
Артикул | Название | Стоимость в закупке | Доставка | Себестоимость | Количество
```

Себестоимость хранится как `Стоимость в закупке + Доставка`. При повторной поставке того же артикула создается новая партия, чтобы продажи могли списывать себестоимость по FIFO.

### Продажи

Минимальные колонки:

```text
Артикул | Название | Доход | Количество
```

Количество можно не указывать, тогда считается одна продажа. При загрузке продаж остаток на складе уменьшается, а себестоимость берется из ближайшей доступной партии.

## Логика учета

### Остатки

У товара есть два независимых остатка:

- `quantity` - количество на складе;
- `ozon_quantity` - количество на OZON.

Статусы товара:

- `in_stock_warehouse` - в наличии на складе;
- `in_stock_ozon` - в наличии на OZON, но не в продаже;
- `in_sale` - в продаже;
- `sold` - продан.

### Себестоимость

Поставки сохраняются как партии. Для каждой продажи фиксируется `cost_price` на момент продажи. Это защищает старые продажи от изменения текущей себестоимости товара.

### Прибыль и расходы OZON

Для OZON-продаж приложение использует финансовые начисления:

- `gross_price` - цена продажи;
- `deductions_total` - расходы OZON;
- `net_income` - чистый доход после расходов OZON;
- `services/items` - детализация начислений.

Прибыль в отчете продаж считается как:

```text
Чистый доход - Себестоимость
```

Если финансовых данных OZON еще нет, чистый доход временно равен цене продажи. После синхронизации начислений отчет использует обновленные данные без необходимости менять старые записи вручную.

## Отчеты

### Отчет продаж

XLSX-отчет содержит:

- артикул;
- название;
- состояние;
- себестоимость;
- цену продажи;
- расходы OZON;
- чистый доход;
- прибыль;
- дату продажи;
- дату начисления;
- ID начисления.

### Отчет остатков

XLSX-отчет содержит закупочную стоимость, доставку, себестоимость, остаток на складе, остаток на OZON и общий остаток.

## Структура проекта

```text
Encounting/                Django project settings
web/                       основное приложение
web/models.py              модели товаров, партий и продаж
web/views.py               views, импорт, экспорт, статистика
web/services/inventory.py  FIFO и учет партий
web/services/ozon_sync.py  синхронизация OZON
web/services/ozon_client.py клиент OZON API
web/templates/             HTML-шаблоны
web/static/                CSS и JS
deploy/                    примеры deploy-конфигурации
```

## Проверка перед изменениями

Перед отправкой изменений желательно выполнить:

```powershell
.\venv\Scripts\python.exe manage.py test web
git status --short
```

Если меняется импорт, экспорт или расчет прибыли, добавляйте тесты в `web/tests.py`. Для отчетов лучше проверять не только наличие файла, но и конкретные значения в XLSX через `openpyxl`.

## Deploy

Примеры конфигурации находятся в `deploy/`. Основной сценарий описан в:

```text
deploy/DEPLOY_BEGET.md
```

Перед deploy проверьте production `.env`, миграции, сбор статики и доступность OZON API-ключей.
