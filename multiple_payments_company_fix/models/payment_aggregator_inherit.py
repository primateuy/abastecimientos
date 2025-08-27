# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PaymentAggregator(models.Model):
    _inherit = 'mps.payment.aggregator'

    # Ensure the record always has a company and aligns with the user context
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model
    def create(self, vals):
        # Set default company to the current env company when missing
        vals.setdefault('company_id', self.env.company.id)
        return super().create(vals)