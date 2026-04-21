# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    custom_rounding_product_id = fields.Many2one(
        'product.product',
        domain="[('custom_is_rounding_product', '=', True)]",
        string="Rounding Product",
        related="company_id.custom_rounding_product_id",
        readonly=False,
    )

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
