# -*- coding: utf-8 -*-
from odoo import models, fields

class PurchaseOrderType(models.Model):
    _inherit = 'purchase.order.type'    

    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de facturación",
        check_company=True,
    )
