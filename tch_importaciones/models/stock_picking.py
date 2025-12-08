# python
from odoo import models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    from odoo import models

    class StockPicking(models.Model):
        _inherit = "stock.picking"

        def action_open_move_lines(self):
            self.ensure_one()

            return {
                "name": "Líneas de movimiento",
                "type": "ir.actions.act_window",
                "res_model": "stock.valuation.adjustment.lines",
                "view_mode": "tree,form",
                "views": [
                    (
                        self.env.ref(
                            "tch_importaciones.view_stock_valuation_adjustment_lines_tree_custom"
                        ).id,
                        "tree",
                    ),
                    (False, "form"),
                ],
                "domain": [
                    "&",
                    ("cost_id.picking_ids", "in", self.ids),
                    ("referencia_layer", "=", self.name),
                ],
                "search_view_id": self.env.ref(
                    "tch_importaciones.view_val_adj_lines_search_cost"
                ).id,
            }

    def action_test_button(self):
        self.ensure_one()
        # Solo para verificar que el botón anda
        raise UserError("✅ El botón de Odoo funciona")