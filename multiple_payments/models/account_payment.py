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

    # Campos de apoyo por el entorno modificado
    is_internal_transfer_mps = fields.Boolean(default=False)
    partner_mps_id = fields.Many2one(
        'res.partner',
        string='Partner Mps',
    )
    payment_type_mps = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound'),
    ])
    date_mps = fields.Date()
    l10n_latam_check_mps_id = fields.Many2one(
        'account.payment',
        string='Check',
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
    
    @api.onchange('date_mps')
    def onchange_date_mps(self):
        if not self.date_mps:
            if self.payment_aggregator_id:
                self.date_mps = self.payment_aggregator_id.date
            else:
                self.date_mps = self.date
    
    @api.constrains("payment_type_mps")
    def _constrains_payment_type_mps(self):
        if self.payment_type_mps:
            if self.payment_aggregator_id and (self.payment_type != self.payment_type_mps):
                self.payment_type = self.payment_type_mps

    @api.onchange('date')
    def onchange_date(self):
        self._constrains_date_mps()
    
    @api.constrains("date")
    def _constrains_date_mps(self):
        if self.payment_aggregator_id:
            self.date_mps = self.payment_aggregator_id.date
        elif self.date_mps:
            self.date = self.date_mps