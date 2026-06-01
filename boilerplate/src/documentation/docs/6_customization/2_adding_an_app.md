# Adding an App

Step-by-step workflow for adding a new Django app to djast.

## 1. Create the App

```bash
cd src
python manage.py startapp myapp
```

## 2. Add to Feature Toggles

```python
# src/src/settings.py
apps = [
    # ... existing apps ...
    ('myapp', True),
]
```

## 3. Create Service Layer

```python
# myapp/services.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MyResult:
    """Result of a myapp operation."""
    status: str


def do_something(*, user_id: int) -> MyResult:
    """Perform the core business logic."""
    ...
    return MyResult(status="ok")
```

## 4. Create Views (Thin)

```python
# myapp/views.py
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from myapp.services import do_something


def my_view(request: HttpRequest) -> HttpResponse:
    result = do_something(user_id=request.user.id)
    return render(request, "myapp/page.html", {"result": result})
```

## 5. Wire URLs

```python
# myapp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.my_view, name="myapp_index"),
]
```

```python
# src/src/urls.py — add after other includes
if 'myapp' in settings.INSTALLED_APPS:
    urlpatterns.append(path('myapp/', include('myapp.urls')))
```

## 6. Add Templates

```
myapp/templates/myapp/page.html
```

## 7. Add Tests

```
myapp/tests/
├── __init__.py
├── test_services.py
└── test_views.py
```

## 8. Update Documentation

| Change | Update |
|--------|--------|
| New app | [Built-in Apps](/docs/apps/) index + new `3_apps/N_myapp.md` |
| New URL | [URL Map](/docs/architecture/url_map) |
| New env var | [Environment](/docs/get_started/environment) + `.env.example` |
| New toggle | [Feature Toggles](/docs/configuration/feature_toggles) |

See [Maintaining Docs](/docs/maintaining_docs/).

## App Structure Reference

```
myapp/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── services.py       # business logic
├── serializers.py    # if API
├── urls.py
├── views.py
├── tasks.py          # if background tasks
├── tests/
├── migrations/
├── templates/myapp/
└── static/myapp/     # optional
```
