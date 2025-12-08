# python
from odoo import models, fields, api
from odoo.exceptions import UserError


class StockValuationAdjustmentLines(models.Model):
    _inherit = "stock.valuation.adjustment.lines"

    final_cost_mr = fields.Monetary(
        string="Costo final MR",
        help="Costo final del producto para MR después de aplicar los costos en destino.",
    )
    former_cost_mr = fields.Monetary(
        string="Costo anterior MR",
        help="Costo anterior del producto para MR antes de aplicar los costos en destino.",
    )
    additional_landed_cost_mr = fields.Monetary(
        string="Costo adicional MR",
        help="Costo adicional asignado al producto para MR en esta línea de ajuste de valoración.",
    )
    cotizacion_mr = fields.Float(
        string='Cotización del día',
        digits=(12, 6),
        help='Cotización del día de la moneda reporte.',
        store=True,
        group_operator=False
    )


    def _create(self, vals):
        company_id = vals.get('company_id') or self.env.company.id
        company = self.env['res.company'].browse(company_id)
        moneda_reporte = company.monedaDeReporte

        # ENTRADA de stock (compra, ajuste positivo, etc.)
        if moneda_reporte and 'value' in vals and vals.get('value', 0) > 0:
            fecha = vals.get('create_date') or fields.Date.context_today(self)
            cotizacion = self.env['res.currency']._get_conversion_rate(
                company.currency_id,
                moneda_reporte,
                company,
                fecha
            )

            if not cotizacion:
                    raise UserError("No hay cotización disponible para la moneda de reportes en la fecha del pago.")

        vals.update({
            'cotizacion_mr': cotizacion,
            'former_cost_mr': float(vals['former_cost']) * cotizacion,
            'final_cost_mr': float(vals['final_cost']) * cotizacion,
            'additional_landed_cost_mr': float(vals['additional_landed']) * cotizacion,
        })

        res = super().create(vals)
        return res