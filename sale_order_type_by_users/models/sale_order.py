from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.depends("partner_id", "company_id")
    @api.depends_context("partner_id", "company_id", "company")
    def _compute_sale_type_id(self):
        for record in self:
            sale_type = False

            # Buscar si el usuario está asignado a algún tipo de orden de venta
            user_types = self.env["sale.order.type"].search([
                ("user_ids", "in", record.env.user.id),
                ("company_id", "in", [record.company_id.id, False]),
            ])
            if user_types:
                # Si el usuario tiene alguno, aplicar el flujo por usuario
                user_sale_type = user_types[:1]
                sale_type = user_sale_type
            else:
                # Si no, aplicar el flujo por cliente
                partner_sale_type = (
                    record.partner_id.with_company(record.company_id).sale_type
                    or record.partner_id.commercial_partner_id.with_company(record.company_id).sale_type
                )
                if partner_sale_type:
                    sale_type = partner_sale_type



            record.type_id = sale_type