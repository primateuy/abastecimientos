# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MpsPaymentAggregator(models.Model):
    _inherit = "mps.payment.aggregator"

    # Aseguramos compañía por defecto; si ya existe el campo, solo sobreescribe el default
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
    )

    @api.model
    def create(self, vals):
        # Forzamos company_id antes de que se evalúen record rules
        vals = dict(vals)
        vals.setdefault("company_id", self.env.company.id)
        return super().create(vals)

    # SAFETY: algunos entornos tienen campos compute apuntando a este método pero no existe.
    # Definimos un no-op para evitar AttributeError al abrir registros viejos.
    def _compute_debt_allocation(self):
        # No realizamos cómputo aquí: el módulo original debería hacerlo.
        # Esto es solo para evitar crasheos mientras se actualiza el módulo principal.
        return
