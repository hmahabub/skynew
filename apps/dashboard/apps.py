from django.apps import AppConfig

class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dashboard'  # Note: 'apps.hr' not just 'hr'
    label = 'dashboard'

    def ready(self):
        from skytexerp.compat import patch_template_context_copy
        patch_template_context_copy()