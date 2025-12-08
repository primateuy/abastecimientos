from odoo import api, fields, models


class StockLandedCost(models.Model):
    _inherit = "stock.landed.cost"

    def compute_remaining_value(self):
        for rec in self:
            # Tomamos solo la fecha (sin hora)
            fecha = fields.Date.to_date(rec.create_date)

            # Moneda de reporte de la compañía
            currency_id = rec.company_id.monedaDeReporte.id

            # Buscar la ÚLTIMA cotización <= fecha, para esa moneda
            tipo_cambio = self.env['res.currency.rate'].search([
                ('currency_id', '=', currency_id),
                ('name', '<=', fecha),
            ], order='name desc', limit=1)
            for sval in rec.valuation_adjustment_lines:
                if tipo_cambio:
                    sval.final_cost_mr = sval.final_cost * tipo_cambio.rate
                    sval.former_cost_mr = sval.former_cost * tipo_cambio.rate
                    sval.additional_landed_cost_mr = sval.additional_landed_cost * tipo_cambio.rate
                    sval.cotizacion_mr = tipo_cambio.inverse_company_rate
                else:
                    # Si nunca hubo cotización previa, dejar 0 o lo que quieras
                    sval.final_cost_mr = 0
                    sval.former_cost_mr = 0
                    sval.additional_landed_cost_mr = 0


