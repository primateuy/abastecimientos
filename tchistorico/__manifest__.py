# -*- coding: utf-8 -*-
{
    'name': "TChistorico",
    'summary': "Histórico de mercadería en moneda secundaria",
    'description': """
Long description of module's purpose
    """,
    'author': "Avance Software",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'stock', 'stock_landed_costs', 'stock_account', 'account_accountant', 'purchase', 'sale_management'],
    'data': [
        'views/views.xml',
        'views/templates.xml',
        'views/stock_quant_view.xml',
        'wizard/recompute_svl.xml',
        'wizard/recompute_landed_cost.xml',
        'views/stock_quant_product_location_report.xml',
        'security/ir.model.access.csv',
        'views/stock_valuation_adjustment_lines.xml',
    ]
}

