# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    custom_rounding_product_id = fields.Many2one(
        'product.product',
        domain="[('custom_is_rounding_product', '=', True)]",
        string="Rounding Product",
    )

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
