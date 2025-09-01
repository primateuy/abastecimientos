from odoo import fields, models

class StockLot(models.Model):
    _inherit = "stock.lot"

    lot_unit_cost = fields.Float(
        string="Costo manual del Lote, sirve para ajuste de inventario",
        digits="Product Price",
        help=(
            "Costo unitario específico para este lote. Este costo no tiene en cuenta costos en destino."
            " Se usará al valorar incrementos de inventario provenientes de ajustes."
        ),
    )
