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

    # NUEVOS CAMPOS para compatibilidad con Internal Transfer FIX
    amount_destino = fields.Monetary(
        string='Destination Amount',
        currency_field='currency_destino_id',
        help='Amount in destination currency for internal transfers'
    )
    currency_destino_id = fields.Many2one(
        'res.currency',
        string='Destination Currency',
        help='Currency of destination journal for internal transfers'
    )

    # Campos de apoyo por el entorno modificado (mantener existentes)
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
            else:
                self.transaction_type = 'vendor_payment'
        else:
            self.transaction_type = 'internal_transfer'
            self.is_internal_transfer = True

    # NUEVO: Método personalizado para crear asientos compatibles
    def move_create_custom(self, paired_payment=None):
        """
        Crear asientos de transferencia interna COMPATIBLE con Odoo estándar
        """
        # Usar el método estándar de Odoo para crear el asiento
        self._prepare_move_line_default_vals()
        move = self.env['account.move'].create(self._prepare_internal_transfer_move_vals())
        
        # Asignar el asiento al pago
        self.move_id = move
        
        return move

    def _prepare_internal_transfer_move_vals(self):
        """
        Preparar valores del asiento para transferencia interna COMPATIBLE
        """
        # Obtener cuentas correctas según el tipo de diario
        source_account = self._get_source_account()
        destination_account = self._get_destination_account()
        
        # Preparar líneas del asiento
        line_vals = []
        
        # Línea de débito (salida de dinero)
        debit_line = {
            'name': self.ref or _('Internal Transfer from Multiple Payments'),
            'account_id': destination_account.id,
            'debit': self.amount,
            'credit': 0.0,
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id if self.currency_id != self.company_currency_id else False,
            'amount_currency': self.amount if self.currency_id != self.company_currency_id else 0.0,
        }
        
        # Línea de crédito (entrada de dinero)
        credit_line = {
            'name': self.ref or _('Internal Transfer from Multiple Payments'),
            'account_id': source_account.id,
            'debit': 0.0,
            'credit': self.amount,
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id if self.currency_id != self.company_currency_id else False,
            'amount_currency': -self.amount if self.currency_id != self.company_currency_id else 0.0,
        }
        
        line_vals.extend([
            (0, 0, debit_line),
            (0, 0, credit_line),
        ])
        
        # Valores del asiento
        move_vals = {
            'date': self.date,
            'ref': self.ref or _('Internal Transfer from Multiple Payments'),
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'line_ids': line_vals,
            'payment_id': self.id,
        }
        
        return move_vals

    def _get_source_account(self):
        """Obtener cuenta de origen según el diario"""
        if self.payment_type == 'outbound':
            return self.journal_id.default_account_id
        else:
            return self.journal_id.default_account_id

    def _get_destination_account(self):
        """Obtener cuenta de destino según el diario de destino"""
        destination_journal = self.env['account.journal'].browse(self.destination_journal_id)
        return destination_journal.default_account_id

    # OVERRIDE del método problemático para compatibilidad
    def _create_paired_internal_transfer_payment(self):
        """
        Método que detecta si viene de multiple_payments y aplica lógica específica
        """
        if self.payment_aggregator_id:
            return self._create_paired_internal_transfer_payment_mps()
        else:
            return super()._create_paired_internal_transfer_payment()

    def _create_paired_internal_transfer_payment_mps(self):
        """
        Versión específica para multiple_payments que es compatible con Internal Transfer FIX
        """
        for payment in self:
            if not payment.paired_internal_transfer_payment_id:
                # Obtener datos del método de pago de multiple_payments
                payment_method = self._get_payment_method_from_aggregator()
                
                # Configurar campos de destino para Internal Transfer FIX
                destination_currency = payment.destination_journal_id.currency_id or payment.company_currency_id
                
                # Calcular amount_destino según la lógica de multiple_payments
                if payment_method and payment_method._checkSameCurrency():
                    amount_destino = payment.amount
                else:
                    # Aplicar conversión usando datos de multiple_payments
                    amount_destino = payment_method.amount if payment_method else payment.amount
                
                paired_payment = payment.copy({
                    'journal_id': payment.destination_journal_id.id,
                    'destination_journal_id': payment.journal_id.id,
                    'currency_id': destination_currency.id,
                    'amount': amount_destino,
                    'amount_destino': payment.amount,  # Para Internal Transfer FIX
                    'currency_destino_id': payment.currency_id.id,  # Para Internal Transfer FIX
                    'payment_type': 'inbound' if payment.payment_type == 'outbound' else 'outbound',
                    'move_id': False,
                    'ref': payment.ref,
                    'paired_internal_transfer_payment_id': payment.id,
                    'date': payment.date,
                    'date_mps': payment.date_mps,
                    'payment_aggregator_id': payment.payment_aggregator_id.id,
                    'partner_id': payment.partner_id.id,
                    'partner_mps_id': payment.partner_mps_id.id,
                })
                
                # Crear asiento usando método personalizado COMPATIBLE
                paired_payment.move_create_custom(payment)
                paired_payment.move_id._post(soft=False)
                payment.paired_internal_transfer_payment_id = paired_payment
                
                # Mensajes de enlace
                body = _("This payment has been created from:") + payment._get_html_link()
                paired_payment.message_post(body=body)
                body = _("A second payment has been created:") + paired_payment._get_html_link()
                payment.message_post(body=body)
                
                # Reconciliar usando la lógica estándar
                lines = (payment.move_id.line_ids + paired_payment.move_id.line_ids).filtered(
                    lambda l: l.account_id == payment.destination_account_id and not l.reconciled
                )
                if lines:
                    lines.reconcile()

    def _get_payment_method_from_aggregator(self):
        """
        Obtener el método de pago relacionado del agrupador
        """
        if not self.payment_aggregator_id:
            return False
            
        return self.payment_aggregator_id.mps_payment_methods_line_ids.filtered(
            lambda m: m.account_journal_id.id == self.journal_id.id
        )
    
    @api.model
    def create(self, values):
        result = super(AccountPayment, self).create(values)
        
        # Validamos tipo de transaccion
        if result.is_internal_transfer and result.transaction_type == False:
            result.write({
                "transaction_type":"internal_transfer"
            })

        # Volvemos a validar
        if values.get("is_internal_transfer") == True and not result.is_internal_transfer:
            result.write({
                "is_internal_transfer": True,
                "transaction_type":"internal_transfer"
            })
        return result
    
    def _multiple_payments_action_post(self):
        # Publicamos el asiento
        self.move_id._post(soft=False)

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