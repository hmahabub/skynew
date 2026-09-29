from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

@login_required
def dashboard(request):
    """
    Warehouse/Inventory is the only module in active use for now, so '/'
    goes straight there instead of the Accounts-driven dashboard.
    """
    return redirect('inventory:inventory_dashboard')