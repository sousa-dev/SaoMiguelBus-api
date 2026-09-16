from django.apps import AppConfig


class McpServerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mcp_server'

    def ready(self):
        from mcp_server import resources, tools  # noqa: F401