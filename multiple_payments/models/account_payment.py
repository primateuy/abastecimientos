
from odoo import _, api, fields, models
import logging
_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    transaction_type = fields.Selection(
        [
            ('internal_transfer', 'Internal Transfer'),
            ('customer_payment', 'Customer Payment'),
            ('vendor_payment', 'Vendor Payment'),
        ],
        compute='_compute_transaction_type',
        store=True,
        readonly=True,
    )

    payment_aggregator_id = fields.Many2one('mps.payment.aggregator', string='Payment Aggregator')

    @api.depends('is_internal_transfer', 'payment_type')
    def _compute_transaction_type(self):
        for record in self:
            if record.is_internal_transfer:
                record.transaction_type = 'internal_transfer'
            elif record.payment_type == 'inbound':
                record.transaction_type = 'customer_payment'
            elif record.payment_type == 'outbound':
                record.transaction_type = 'vendor_payment'
            else:
                record.transaction_type = False

    def set_transaction_type(self):
        """Compat: algunos flujos pueden llamarlo explícitamente."""
        for record in self:
            if record.is_internal_transfer:
                record.transaction_type = 'internal_transfer'
            elif record.payment_type == 'inbound':
                record.transaction_type = 'customer_payment'
            elif record.payment_type == 'outbound':
                record.transaction_type = 'vendor_payment'
            else:
                record.transaction_type = False
        return True
