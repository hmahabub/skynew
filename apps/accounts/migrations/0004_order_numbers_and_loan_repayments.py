from django.db import migrations


def forwards(apps, schema_editor):
    Project = apps.get_model('accounts', 'Project')
    LetterOfCredit = apps.get_model('accounts', 'LetterOfCredit')
    LCLoan = apps.get_model('accounts', 'LCLoan')
    LCLoanRepayment = apps.get_model('accounts', 'LCLoanRepayment')

    # The number users typed becomes the buyer's reference; Order No. is now
    # generated as YY + ORD + id (see Project.save).
    for order in Project.objects.all():
        if not order.buyer_ref:
            order.buyer_ref = order.project_number
        order.project_number = f"{order.created_at:%y}ORD{order.pk:05d}"
        if order.status == 'quotation':
            order.status = 'order'
        order.save(update_fields=['buyer_ref', 'project_number', 'status'])

    LetterOfCredit.objects.filter(status='utilized').update(status='completed')

    # Loans used to carry a typed-in repaid amount - keep it as one repayment.
    for loan in LCLoan.objects.filter(repaid_amount__gt=0):
        if not LCLoanRepayment.objects.filter(loan=loan).exists():
            LCLoanRepayment.objects.create(
                loan=loan, kind='payment', repayment_date=loan.loan_date, amount=loan.repaid_amount,
                mode='bank', bank_name=loan.bank_name, remarks='Carried over from earlier records',
            )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_remove_cost_payment_status_cost_bank_name_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
