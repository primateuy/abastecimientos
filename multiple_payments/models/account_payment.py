from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

import logging
from odoo.addons.account.models.account_payment import AccountPayment
_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    transaction_type = fields.Selection([('internal_transfer', 'Internal Transfer'),
                                         ('customer_payment', 'Customer Payment'),
                                         ('vendor_payment', 'Vendor Payment')])

    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='Payment Aggregator'
    )
    
    def _check_payment_method_line_id(self):
        return super()._check_payment_method_line_id()

    def set_transaction_type(self):
        if not self.is_internal_transfer:
            if self.partner_type == 'customer':
                self.transaction_type = 'customer_payment'
                # self.is_internal_transfer = False
            else:
                self.transaction_type = 'vendor_payment'
                # self.is_internal_transfer = False
        else:
            self.transaction_type = 'internal_transfer'
            self.is_internal_transfer = True
    
    @api.model
    def create(self, values):

        # _logger.info("Create pago")
        # _logger.info("values")
        # _logger.info(values)
        # Creamos registro
        result = super(AccountPayment, self).create(values)
        
        # Validamos tipo de transaccion
        if result.is_internal_transfer and result.transaction_type == False:
            result.write({
                "transaction_type":"internal_transfer"
            })

        # Volvemos a validar
        if values["is_internal_transfer"] == True and not result.is_internal_transfer:
            result.write({
                "is_internal_transfer": True,
                "transaction_type":"internal_transfer"
            })
        return result
    
    def _multiple_payments_action_post(self):
        # Publicamos el asiento
        self.move_id._post(soft=False)

        # Creamos las transferencias internas en caso de que hayan
        # self.filtered(
        #     lambda pay: pay.is_internal_transfer and not pay.paired_internal_transfer_payment_id
        # )._create_paired_internal_transfer_payment()

    def action_draft(self):
        if self.payment_aggregator_id and self.is_internal_transfer:
            raise ValidationError(_("Payments created with a payment aggregator cannot be set as draft."))
        
        return super().action_draft()