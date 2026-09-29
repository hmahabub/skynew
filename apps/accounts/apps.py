from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'  # Note: 'apps.hr' not just 'hr'
    label = 'accounts'