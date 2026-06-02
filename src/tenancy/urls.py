from django.urls import path

from tenancy import views

urlpatterns = [
    path(
        'celery/cancel-all',
        views.cancel_all_celery_jobs,
        name='ops_celery_cancel_all',
    ),
]
