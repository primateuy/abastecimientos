# -*- coding: utf-8 -*-
from odoo import models, fields, api


class Product(models.Model):
    _inherit = 'product.product'

    custom_is_rounding_product = fields.Boolean(
        string='Is Round Off Product?',
        copy=False,
    )

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
