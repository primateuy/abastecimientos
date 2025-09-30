# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Lote de pagos - Recibos y Ordenes de pago",
    "version": "17.0.1.1.3",
    "category": "Accounting",
    "website": "https://dityc.com",
    "author": "DITyC SRL",
    "license": "AGPL-3",
    "depends":
        [
            "account", # core
            "account_payment_pro", # adhoc
            'l10n_ar_withholding_ux', # adhoc
            'l10n_ar_account_withholding', # adhoc
        ],
    "data":
        [
            "views/batch_receipt.xml",
            "views/account_payment_batch_st_views.xml",
            'views/mail_template_data.xml',
            "views/account_payment_views.xml",
            "views/res_company.xml",
            'security/ir.model.access.csv',
            "data/account_payment_batch_data.xml",
        ],
    "installable": True,
}
