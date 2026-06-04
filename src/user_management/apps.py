# In your app's apps.py
from django.apps import AppConfig

class UserManagementConfig(AppConfig):
    name = 'user_management'

    def ready(self):
        # signals.py depends on allauth; only wire it when allauth is installed
        # (i.e. AUTHENTICATION_REQUIRED). The REST auth surface works without it.
        from django.conf import settings

        if 'allauth.account' in settings.INSTALLED_APPS:
            import user_management.signals  # noqa: F401