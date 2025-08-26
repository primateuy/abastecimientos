from odoo import _, api, fields, models
import logging
_logger = logging.getLogger(__name__)

class accountPayment(models.Model):
    _inherit = 'account.payment'
    
    transaction_type = fields.Selection([('internal_transfer', 'Internal Transfer'),
                                         ('customer_payment', 'Customer Payment'),
                                         ('vendor_payment', 'Vendor Payment')])
    
    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='Payment Aggregator'
    )
    
    def set_transaction_type(self):
        if not self.is_internal_transfer:
            if self.partner_type == 'customer':
                self.transaction_type = 'customer_payment'
            else:
                self.transaction_type = 'vendor_payment'
        else:
            self.transaction_type = 'internal_transfer'
    
    @api.model
    def create(self, values):
        result = super().create(values)
        
        if result.is_internal_transfer and result.transaction_type == False:
            result.write({
                "transaction_type":"internal_transfer"
            })
        
        return result