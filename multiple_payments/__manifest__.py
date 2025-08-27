{
    "name": "Multiple Payments",
    "version": "1.2.2",
    "author": "Tu Nombre / Empresa",
    "category": 'Accounting/Accounting',
    "depends": ["base","account","l10n_latam_check","l10n_uy"],
    "data":[
        # Grupos
        # Permisos 
        "security/admin/ir.model.access.csv",
        "security/group_user/ir.model.access.csv",
        # Reglas
        "data/ir_rules.xml",
        # Data
        "data/receipt_books.xml",
        "data/res_country.xml",
        "data/document_type.xml",
        "data/ir_sequence_data.xml",
        # Views
        "views/payment_aggregator_views.xml",
        "views/receipt_books_views.xml",
        "views/res_currency_views.xml",
        "views/account_journal_views.xml",
        "views/ir_menu_views.xml",
        "views/payment_view.xml",
        # Reports
    ],
    "installable": True,
    "application": False,

    'version': '16.0.20250827000812'
}