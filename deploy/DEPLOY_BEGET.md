# Deploy to Beget VPS

Target server assumptions:

- Ubuntu 24.04
- Nginx is already installed and serves `jget-it.ru`
- Python 3.12 is available as `python3`
- The app will run from `/home/ozon-encounting`
- Gunicorn will listen on `127.0.0.1:8083`
- Public URL: `https://jgetbot.store/`
- Database: SQLite at `/home/ozon-encounting/db.sqlite3`

## 1. Copy project

Create `/home/ozon-encounting` on the VPS and put the project files there.

Do not commit or publish the real `.env` file.

## 2. Create environment

```bash
cd /home/ozon-encounting
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
cp deploy/ozon-encounting.env.example .env
```

Edit `/home/ozon-encounting/.env`:

- set a real `SECRET_KEY`
- set `OZON_CLIENT_ID`
- set `OZON_API_KEY`
- keep `FORCE_SCRIPT_NAME` empty for deployment at the domain root

Point DNS for `jgetbot.store` and `www.jgetbot.store` to the VPS public IPv4 before issuing SSL.

Generate a secret key on the server:

```bash
./venv/bin/python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
```

## 3. Prepare Django

```bash
cd /home/ozon-encounting
./venv/bin/python manage.py migrate
./venv/bin/python manage.py collectstatic --noinput
./venv/bin/python manage.py check --deploy
```

Create an admin user if needed:

```bash
./venv/bin/python manage.py createsuperuser
```

## 4. Install systemd services

```bash
cp /home/ozon-encounting/deploy/ozon-encounting.service /etc/systemd/system/
cp /home/ozon-encounting/deploy/ozon-encounting-sync.service /etc/systemd/system/
cp /home/ozon-encounting/deploy/ozon-encounting-sync.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ozon-encounting.service
systemctl enable --now ozon-encounting-sync.timer
```

Check status:

```bash
systemctl status ozon-encounting.service --no-pager
journalctl -u ozon-encounting.service -n 100 --no-pager
```

Run Ozon sync manually:

```bash
systemctl start ozon-encounting-sync.service
journalctl -u ozon-encounting-sync.service -n 100 --no-pager
```

## 5. Add temporary HTTP Nginx site

Install the HTTP-only site first. This config does not reference missing SSL files, so `nginx -t` can pass before the certificate exists.

```bash
cp /home/ozon-encounting/deploy/nginx-server-jgetbot-http.conf /etc/nginx/sites-available/jgetbot.conf
ln -s /etc/nginx/sites-available/jgetbot.conf /etc/nginx/sites-enabled/jgetbot.conf
mkdir -p /var/www/letsencrypt
nginx -t
systemctl reload nginx
```

## 6. Issue SSL certificate

After DNS starts resolving to the VPS, issue the certificate:

```bash
certbot certonly --webroot -w /var/www/letsencrypt -d jgetbot.store -d www.jgetbot.store
```

## 7. Enable HTTPS Nginx site

Replace the temporary HTTP config with the HTTPS config:

```bash
cp /home/ozon-encounting/deploy/nginx-server-jgetbot.conf /etc/nginx/sites-available/jgetbot.conf
```

Then check and reload:

```bash
nginx -t
systemctl reload nginx
```

The app should open at:

```text
https://jgetbot.store/
```

## 8. Useful operations

Restart the app:

```bash
systemctl restart ozon-encounting.service
```

Apply code updates:

```bash
cd /home/ozon-encounting
./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py migrate
./venv/bin/python manage.py collectstatic --noinput
systemctl restart ozon-encounting.service
```

The VPS has no swap right now. If Excel imports fail because of memory pressure, add a small swap file before increasing Gunicorn workers.
