# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockValuationLayerFix(models.Model):
    _inherit = "stock.valuation.layer"

    # Some inherited views (e.g., from tchistorico) reference `quantity_display`,
    # which does not exist in v17 core. Define it here to mirror `quantity`
    # and keep numeric sorting/filters working.
    quantity_display = fields.Float(
        string="Cantidad",
        compute="_compute_quantity_display",
        digits="Product Unit of Measure",
        store=False,
        readonly=True,
    )

    @api.depends("quantity")
    def _compute_quantity_display(self):
        for rec in self:
            rec.quantity_display = rec.quantity or 0.0
