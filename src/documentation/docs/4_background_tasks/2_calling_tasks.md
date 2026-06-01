# Calling Tasks

Dispatch tasks from views, services, or management commands.

## From a Service (Recommended)

```python
# myapp/services.py
from myapp.tasks import send_welcome_email


def register_user(*, username: str, email: str) -> User:
    user = User.objects.create_user(username=username, email=email)
    send_welcome_email.delay(user_id=user.id)
    return user
```

## From a View

Views should delegate to services — but if you must call directly:

```python
from myapp.tasks import send_welcome_email

def signup_view(request):
    # ... create user ...
    send_welcome_email.delay(user_id=user.id)
    return redirect("index")
```

## Dispatch Methods

| Method | Behavior |
|--------|----------|
| `.delay(**kwargs)` | Async — returns immediately |
| `.apply_async(kwargs={...})` | Async with extra options (countdown, queue) |
| `.apply(kwargs={...})` | Sync — blocks until complete (testing only) |

## Countdown / ETA

```python
send_welcome_email.apply_async(
    kwargs={"user_id": user.id},
    countdown=60,  # run in 60 seconds
)
```

## Checking Results

```python
result = send_welcome_email.delay(user_id=1)
result.ready()   # True when complete
result.get()     # Blocks until result available
result.id        # Task ID for monitoring
```

## Error Handling

Failed tasks retry up to `max_retries` (default 3). Check worker logs:

```bash
celery -A src worker --loglevel=info
```

See [Running Locally](/docs/background_tasks/running_locally).
