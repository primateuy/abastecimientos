# -*- coding: utf-8 -*-
{
    "name": "Sale: Product domain by active company",
    "summary": "Restringe el campo product_id en sale.order.line a la empresa activa",
    "version": "17.0.1.0.0",
    "author": "aiglesas - Primate Uy",
    "license": "LGPL-3",
    "category": "Sales",
    "depends": ["sale_management"],
    "data": [
        "views/sale_order_line_views.xml",
    ],
    "installable": True,
    "application": False,
}
