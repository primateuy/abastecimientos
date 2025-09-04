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
    # def move_create_custom(self, paired_payment=None):
    #     """
    #     Crear asientos de transferencia interna COMPATIBLE con Odoo estándar
    #     """
    #     # Usar el método estándar de Odoo para crear el asiento
    #     self._prepare_move_line_default_vals()
    #     move = self.env['account.move'].create(self._prepare_internal_transfer_move_vals())
    #
    #     # Asignar el asiento al pago
    #     self.move_id = move
    #
    #     return move

    # def _prepare_internal_transfer_move_vals(self):
    #     """
    #     Preparar valores del asiento para transferencia interna COMPATIBLE
    #     Asegura que currency_id nunca sea NULL para evitar errores de base de datos.
    #     """
    #     # Obtener cuentas correctas según el tipo de diario
    #     source_account = self._get_source_account()
    #     destination_account = self._get_destination_account()
    #
    #     # Preparar líneas del asiento
    #     line_vals = []
    #
    #     # Determinar la moneda a usar - nunca debe ser None/False
    #     # Si currency_id es None, usar company_currency_id como fallback
    #     currency_id = self.currency_id.id if self.currency_id else self.company_currency_id.id
    #
    #     # Validar que tenemos una moneda válida
    #     if not currency_id:
    #         raise ValidationError(_('No se pudo determinar la moneda para el asiento. Verifique la configuración.'))
    #
    #     # Línea de débito (salida de dinero)
    #     debit_line = {
    #         'name': self.ref or _('Internal Transfer from Multiple Payments'),
    #         'account_id': destination_account.id,
    #         'debit': self.amount,
    #         'credit': 0.0,
    #         'partner_id': self.partner_id.id if self.partner_id else False,
    #         'currency_id': currency_id,  # Siempre usar un ID válido
    #         'amount_currency': self.amount if self.currency_id != self.company_currency_id else 0.0,
    #     }
    #
    #     # Línea de crédito (entrada de dinero)
    #     credit_line = {
    #         'name': self.ref or _('Internal Transfer from Multiple Payments'),
    #         'account_id': source_account.id,
    #         'debit': 0.0,
    #         'credit': self.amount,
    #         'partner_id': self.partner_id.id if self.partner_id else False,
    #         'currency_id': currency_id,  # Siempre usar un ID válido
    #         'amount_currency': -self.amount if self.currency_id != self.company_currency_id else 0.0,
    #     }
    #
    #     line_vals.extend([
    #         (0, 0, debit_line),
    #         (0, 0, credit_line),
    #     ])
    #
    #     # Valores del asiento
    #     move_vals = {
    #         'date': self.date,
    #         'ref': self.ref or _('Internal Transfer from Multiple Payments'),
    #         'journal_id': self.journal_id.id,
    #         'currency_id': currency_id,  # Usar la misma moneda validada
    #         'partner_id': self.partner_id.id if self.partner_id else False,
    #         'line_ids': line_vals,
    #         'payment_id': self.id,
    #     }
    #
    #     return move_vals

    def _get_source_account(self):
        """Obtener cuenta de origen según el diario"""
        if self.payment_type == 'outbound':
            return self.journal_id.default_account_id
        else:
            return self.journal_id.default_account_id

    def _get_destination_account(self):
        """Obtener cuenta de destino según el diario de destino"""
        destination_journal = self.env['account.journal'].browse(self.destination_journal_id.id)
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
        
    def action_post(self):
        """
        Sobrescribir action_post para preservar currency_rate personalizado
        """
        _logger.info("=== action_post EJECUTADO ===")
        _logger.info("Payment ID: %s", self.id)
        _logger.info("Currency_rate ANTES de action_post: %s", self.currency_rate)
        
        # Guardar el currency_rate personalizado ANTES de cualquier procesamiento
        custom_currency_rate = self.currency_rate
        
        # Ejecutar action_post normal (que incluye tchistorico)
        result = super().action_post()
        
        # Restaurar el currency_rate personalizado DESPUÉS de action_post
        if custom_currency_rate != 1.0:  # Solo si no es el valor por defecto
            _logger.info("Restaurando currency_rate personalizado: %s", custom_currency_rate)
            self.write({
                'currency_rate': custom_currency_rate
            })
            
            # También actualizar el asiento contable
            if self.move_id:
                self.move_id.write({
                    'currency_rate': custom_currency_rate
                })
                
                # Recalcular las líneas del asiento con el currency_rate correcto
                self._recompute_payment_lines(custom_currency_rate)
        
        _logger.info("Currency_rate DESPUÉS de action_post: %s", self.currency_rate)
        return result
    
    def _recompute_payment_lines(self, currency_rate):
        """
        Recalcular las líneas del asiento con el currency_rate correcto
        """
        if not self.move_id:
            return
            
        _logger.info("Recalculando líneas del asiento con currency_rate: %s", currency_rate)
        
        # Aquí puedes agregar la lógica específica para recalcular las líneas
        # basándote en el currency_rate personalizado

    # def _create_internal_transfer_move(self):
    #     """
    #     Crear asiento para transferencia interna con currency_id válido
    #     """
    #     move_vals = self._prepare_internal_transfer_move_vals()
    #     move = self.env['account.move'].create(move_vals)
    #     self.move_id = move
    #     return move

    def _create_payment_move(self):
        """
        Crear asiento para pago normal con currency_id válido
        """
        # Usar el método estándar pero con validaciones adicionales
        move_vals = self._prepare_move_line_default_vals()
        
        # Asegurar que todas las líneas tengan currency_id válido
        for line_vals in move_vals:
            if 'currency_id' not in line_vals or not line_vals['currency_id']:
                line_vals['currency_id'] = self.company_currency_id.id
        
        move = self.env['account.move'].create({
            'date': self.date,
            'ref': self.ref,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'line_ids': [(0, 0, line_vals) for line_vals in move_vals],
            'payment_id': self.id,
        })
        self.move_id = move
        return move

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
        # if result.is_internal_transfer and result.transaction_type == False:
        #     result.write({
        #         "transaction_type":"internal_transfer"
        #     })
        #
        # # Volvemos a validar
        # if values.get("is_internal_transfer") == True and not result.is_internal_transfer:
        #     result.write({
        #         "is_internal_transfer": True,
        #         "transaction_type":"internal_transfer"
        #     })
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

    @api.depends('currency_id', 'company_id', 'date')
    def _compute_currency_rate(self):
        """
        Sobrescribir _compute_currency_rate para preservar valores personalizados
        cuando el pago viene de un payment aggregator
        """
        for payment in self:
            # Si el pago viene de un payment aggregator, NO recalcular automáticamente
            if payment.payment_aggregator_id:
                _logger.info(f"Preservando currency_rate personalizado para pago {payment.name}: {payment.currency_rate}")
                # No hacer nada, mantener el valor actual
                continue
            
            # Para pagos normales, usar el comportamiento estándar
            super(AccountPayment, payment)._compute_currency_rate()

    def write(self, vals):
        """
        Sobrescribir write para rastrear cambios en currency_rate
        """
        if 'currency_rate' in vals:
            _logger.info("=== WRITE currency_rate DETECTADO ===")
            _logger.info("Payment ID: %s", self.id)
            _logger.info("Currency_rate ANTES: %s", self.currency_rate)
            _logger.info("Currency_rate NUEVO: %s", vals['currency_rate'])
            
            # Solo mostrar stack trace si el valor está cambiando
            if self.currency_rate != vals['currency_rate']:
                _logger.info("*** CURRENCY_RATE CAMBIANDO DE %s A %s ***", self.currency_rate, vals['currency_rate'])
                _logger.info("Stack trace completo:")
                import traceback
                for line in traceback.format_stack():
                    _logger.info(line.strip())
        
        return super().write(vals)