# -*- coding: utf-8 -*-
# Part of Probuse Consulting Service Pvt Ltd. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Sale Order Round Off',
    'version': '4.0.0',
    'license': 'Other proprietary',
    'price': 12.0,
    'currency': 'EUR',
    'author' : 'Probuse Consulting Service Pvt. Ltd.',
    'website' : 'www.probuse.com',
    'summary':  """Sale Order Round Off and Customer Invoice Round Off """,
    'description': """
Sale Order Invoice Rounding
Round Off Sales Order Amount
Round Off Customer Invoice Amount
Add Round Off Line in Sales Order Line
Add Round Off Line in Customer Invoice
Round Off
Round Off Value
    """,
    'category': 'Sale/Accounting',
    'depends': [
        'sale',
        'account',
    ],
    'support': 'contact@probuse.com',
    'images': ['static/description/img1.jpg'],
    'live_test_url': 'https://probuseappdemo.com/probuse_apps/sale_order_invoice_rounding/1121',
    'data': [
        'security/ir.model.access.csv',
        'wizard/so_inv_rounding_views.xml',
        'views/order_view.xml',
        'views/account_invoice_view.xml',
        'views/product_view.xml',
        'views/config_settings_views.xml',
    ],
    'installable' : True,
    'application' : False,
    'auto_install' : False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
