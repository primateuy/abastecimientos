# python
from odoo import models, fields
from odoo.exceptions import UserError


class StockValuationAdjustmentLines(models.Model):
    _inherit = "stock.valuation.adjustment.lines"

    referencia_layer = fields.Char(
        string="Referencia",
        related="move_id.stock_valuation_layer_ids.reference",
        readonly=True,
    )

    picking_id = fields.Many2one(
        'stock.picking',
        string="Picking",
        related='move_id.picking_id',
        store=True,
    )