from django.conf import settings


def merchandising(request):
    """Lets templates hide Merchandising-only menus/sections (Purchase Orders, Invoices)."""
    return {'MERCHANDISING_ENABLED': settings.MERCHANDISING_ENABLED}
