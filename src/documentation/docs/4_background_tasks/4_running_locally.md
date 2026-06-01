# Running Celery Locally

Celery requires Redis running locally. Start three processes in separate
terminals.

## 1. Start Redis

**macOS (Homebrew):**

```bash
brew services start redis
```

**Docker:**

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

**Linux:**

```bash
sudo systemctl start redis
```

Verify:

```bash
redis-cli ping
# PONG
```

## 2. Start Celery Worker

```bash
cd src
celery -A src worker --loglevel=info
```

## 3. Start Celery Beat (Periodic Tasks Only)

```bash
cd src
celery -A src beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## 4. Start Django (Separate Terminal)

```bash
cd src
python run.py
```

## Environment

Ensure `.env` has:

```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

## Docker Compose Alternative

Skip local Redis setup — use Docker Compose which starts all five services:

```bash
docker compose up -d
```

See [Docker Compose](/docs/deployment/docker_compose).

## Verify Tasks Execute

```bash
cd src
python manage.py shell
```

```python
from app.tasks import send_welcome_email
result = send_welcome_email.delay(user_id=1)
result.id  # task ID — check worker terminal for output
```

## Troubleshooting

See [Troubleshooting — Celery](/docs/troubleshooting/).
