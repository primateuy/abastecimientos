from odoo import _, api, fields, models
import logging
_logger = logging.getLogger(__name__)
class accountMoveLine(models.Model):

    _inherit = 'account.move.line'
    
    total_import = fields.Monetary(
        string='Total Import', store=True,
        currency_field='currency_id',
    )

    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='payment_aggregator',
        )