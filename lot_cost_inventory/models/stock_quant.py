from odoo import fields, models

class StockQuant(models.Model):
    _inherit = "stock.quant"

    lot_unit_cost = fields.Float(
        string="Costo del Lote",
        related="lot_id.lot_unit_cost",
        readonly=False,          # Para poder editarlo desde la grilla
        digits="Product Price",
    )