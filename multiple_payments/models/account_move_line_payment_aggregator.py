from odoo import _, api, fields, models
import logging
_logger = logging.getLogger(__name__)
class accountMoveLinePaymentAggregator(models.Model):
    _name = 'account.move.line.payment.aggregator'
    _inherits = {'account.move.line': 'account_move_line_id'}
    
    account_move_line_id = fields.Many2one(
        'account.move.line',
        string='payment_aggregator',
        )
    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='payment_aggregator',
        )
    payment_aggregator_total_import = fields.Monetary(
        string='Total Import', store=True,
        currency_field='currency_id',
    )
    payment_aggregator_amount_currency = fields.Monetary(
        string="Amount",
        currency_field='currency_id',
    )
    payment_aggregator_amount_residual = fields.Monetary(
        string="Total Residual Amount",
        currency_field='currency_id',
    )