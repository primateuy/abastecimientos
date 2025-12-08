from odoo import models, fields, api, _


class TchImportacion(models.Model):
    _name = "tch.importacion"
    _description = "Importación"

    name = fields.Char(
        string="Referencia",
        required=True,
        default=lambda self: self._default_name(),
    )
    date = fields.Date(
        string="Fecha",
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    picking_ids = fields.Many2many(
        "stock.picking",
        "tch_importacion_picking_rel",
        "importacion_id",
        "picking_id",
        string="Traslados",
        help="Traslados (operaciones de inventario) asociados a esta importación.",
    )

    total_quantity = fields.Float(
        string="Cantidad total",
        store=False,
        help="Cantidad total de productos involucrados en los traslados.",
    )
    total_cost_destino = fields.Monetary(
        string="Costo total destino",
        store=False,
        currency_field="currency_id",
        help="Suma de los costos en destino de todos los productos.",
    )
    unit_cost_destino = fields.Monetary(
        string="Costo unitario destino",
        store=False,
        currency_field="currency_id",
        help="Costo promedio por unidad considerando todos los traslados.",
    )

    total_additional_landed_cost_mr = fields.Float(
        string="Total Costos MR en destino",
        # compute="_compute_total_additional_landed_cost_mr",
        store=False
    )

    # @api.depends('picking_ids')
    # def _compute_total_additional_landed_cost_mr(self):
    #     ValLine = self.env['stock.valuation.adjustment.lines']
    #     for rec in self:
    #         if not rec.picking_ids:
    #             rec.total_additional_landed_cost_mr = 0
    #             continue
    #
    #         domain = [
    #             '&',
    #             ('cost_id.picking_ids', 'in', rec.picking_ids.ids),
    #             ('referencia_layer', 'in', rec.picking_ids.ids),
    #         ]
    #
    #         lines = ValLine.search(domain)
    #
    #         rec.total_additional_landed_cost_mr = sum(lines.mapped('additional_landed_cost_mr'))

    def action_open_move_lines(self):
        self.ensure_one()

        return {
            "name": "Líneas de movimiento",
            "type": "ir.actions.act_window",
            "res_model": "stock.valuation.adjustment.lines",
            "view_mode": "tree",
            "views": [
                (
                    self.env.ref(
                        "tch_importaciones.view_stock_valuation_adjustment_lines_tree_custom"
                    ).id,
                    "tree",
                ),
            ],
            "domain": [
            ('picking_id', 'in', self.picking_ids.ids),
            ],
            "search_view_id": self.env.ref(
                "tch_importaciones.view_val_adj_lines_search_cost"
            ).id,
        }

    def _default_name(self):
        return self.env["ir.sequence"].next_by_code("tch.importacion") or _("Nueva importación")



