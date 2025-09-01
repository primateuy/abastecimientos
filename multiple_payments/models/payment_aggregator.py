from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from odoo.addons.account.models.account_payment import AccountPayment
import logging
_logger = logging.getLogger(__name__)

class PaymentAggregator(models.Model):

    _name = 'mps.payment.aggregator'
    _description = 'Model to save payment aggregator'

    name = fields.Char(required=True, default="Borrador")
    company_id = fields.Many2one(
        'res.company',
        string='company',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='currency',
        domain="[('id','=',account_journals_currency_ids)]",
        required=False
    )
    account_journal_aggregator_id = fields.Many2one(
        'account.journal.aggregator',
        string='Intermediate diary',
        required=True,
        domain=lambda self: "[('company_id','=', %s),('currency_id','=',currency_id)]" % self.env.company.id
    )

    account_journals_currency_ids = fields.Many2many(
        'res.currency', 
        domain=lambda self: str(self._get_account_journals_currency_domain()),
        compute="_get_account_journals_currency_domain_compute"
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('published','Published')
    ],default="draft")

    # talonario
    receiptbook_id = fields.Many2one(
        "mps.receipt.books",
        required=True
    )

    # domain para el talonario
    domain_receiptbook_id = fields.Char(default="[('is_public','=',True)]")

    # cliente o empresa
    customer_id = fields.Many2one(
        'res.partner',
        string='customer',
        required=True
    )

    adenda = fields.Char(string="Adenda")

    date = fields.Date(required=True)

    # importe
    amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_amount"
    )

    # pago a cuenta
    payment_account = fields.Monetary(
        currency_field="currency_id"
    )

    # asignacion de deuda
    debt_allocation = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_debt_allocation"
    )

    # Diferencia
    difference = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_difference"
    )

    # Metodos de pago
    mps_payment_methods_line_ids = fields.One2many(
        'mps.payment.methods.line', 
        'mps_payment_aggregator_id'
    )

    # apuntes contables
    mps_credits_line_ids = fields.Many2many(
        'account.move.line', 
        string='Cuentas por Pagar/Cobrar',
    )
    average_rate = fields.Float(compute='_compute_average_rate')

    account_move_line_payment_agg_ids = fields.One2many(
        'account.move.line.payment.aggregator',
        'payment_aggregator_id' 
    )

    # Se suma los montos de los metodos de pago
    @api.depends('average_rate')
    def _compute_average_rate(self):
        payment_lines = self.mps_payment_methods_line_ids
        if len(payment_lines) > 0:
            self.average_rate = sum(payment_lines.mapped("exchange_rate")) / len(payment_lines)
        else: 
            self.average_rate = 0


    # Se suma los montos de los metodos de pago
    @api.depends('amount')
    def _compute_amount(self):
        for record in self:
            record.amount = sum(self.mps_payment_methods_line_ids.mapped("amount"))

    # Si el adenda se cambia, se lo agregamos a los metodos de pago 
    @api.onchange('adenda')
    def onchange_adenda(self):
        if self.adenda:
            if len(self.mps_payment_methods_line_ids) > 0:
                for method in self.mps_payment_methods_line_ids:
                    method.adenda = self.adenda
    
    # Metodo computado para buscar los ids de las monedas aceptables
    @api.depends('account_journals_currency_ids')
    def _get_account_journals_currency_domain_compute(self):
        for record in self:
            record.account_journals_currency_ids = self.env["res.currency"].search(record._get_account_journals_currency_domain()).ids

    @api.onchange('account_journals_currency_ids')
    def onchange_account_journals_currency_ids(self):
        self._get_account_journals_currency_domain_compute()

    # Metodo para obtener el domain de los diarios intermedios
    def _get_account_journals_currency_domain(self):
        for record in self:
            account_journals = record.env["account.journal.aggregator"].search([("company_id","=", self.env.company.id)])
            return [('id','in', account_journals.mapped("currency_id.id"))]

    def button_change_state(self):
        """MÉTODO CORREGIDO: Cambiar estatus con validaciones mejoradas y manejo de fechas correcto"""
        if self.state == "draft":
        
            # Validamos pagos
            if len(self.mps_payment_methods_line_ids) == 0:
                raise ValidationError(_("To make payments you must load the payments in the payment lines."))

            if self.difference != 0:
                raise ValidationError(_("Difference must be 0 to publish a payments aggregator."))
            
            # NUEVA VALIDACIÓN: Verificar monedas y tasas de cambio
            self._validate_currencies_and_rates()
            
            try:
                has_invoices = len(self.account_move_line_payment_agg_ids) > 0
                has_payment_methods = len(self.mps_payment_methods_line_ids) > 0
                has_payment_account = self.payment_account > 0
                
                _logger.info(f"=== DIAGNÓSTICO AGRUPADOR {self.name} ===")
                _logger.info(f"Facturas: {has_invoices} ({len(self.account_move_line_payment_agg_ids)} líneas)")
                _logger.info(f"Métodos de pago: {has_payment_methods} ({len(self.mps_payment_methods_line_ids)} líneas)")
                _logger.info(f"Pago a cuenta: {has_payment_account} (${self.payment_account})")
                
                if has_invoices and has_payment_methods:
                    # CASO MIXTO: Facturas + Métodos de pago específicos
                    _logger.info("=== EJECUTANDO CASO MIXTO ===")
                    self._create_mixed_payments()
                    
                elif has_invoices and not has_payment_methods:
                    # CASO 1: Solo facturas (sin métodos específicos)
                    _logger.info("=== EJECUTANDO SOLO FACTURAS ===")
                    self._create_invoices_payment()
                    if has_payment_account:
                        self._create_payment_account_if_needed_with_invoices()
                        
                else:
                    # CASO 2: Solo pago a cuenta (sin facturas)
                    _logger.info("=== EJECUTANDO SOLO PAGO A CUENTA ===")
                    self._create_lines_payment_payments_v2()

                # VERIFICAR ESTADO FINAL DE TODOS LOS PAGOS
                final_payments = self.env['account.payment'].search([
                    ('payment_aggregator_id', '=', self.id)
                ])
                
                draft_payments = final_payments.filtered(lambda p: p.state == 'draft')
                posted_payments = final_payments.filtered(lambda p: p.state == 'posted')
                
                _logger.info(f"=== RESULTADO FINAL ===")
                _logger.info(f"Pagos creados: {len(final_payments)}")
                _logger.info(f"Pagos confirmados: {len(posted_payments)}")
                _logger.info(f"Pagos en borrador: {len(draft_payments)}")
                
                if draft_payments:
                    _logger.warning("ADVERTENCIA: Algunos pagos quedaron en borrador:")
                    for payment in draft_payments:
                        _logger.warning(f"- {payment.name}: {payment.state} - Monto: {payment.amount}")
                
                # Intentar confirmar pagos que quedaron en borrador
                for payment in draft_payments:
                    try:
                        _logger.info(f"Intentando confirmar pago pendiente: {payment.name}")
                        payment.action_post()
                        if payment.state == 'posted':
                            _logger.info(f"✓ Pago confirmado exitosamente: {payment.name}")
                        else:
                            _logger.warning(f"✗ Pago sigue en borrador: {payment.name}")
                    except Exception as e:
                        _logger.error(f"✗ Error confirmando {payment.name}: {str(e)}")

            except Exception as e:
                _logger.error(f"Error en button_change_state: {str(e)}")
                raise UserError(str(e))
                
            self.state = "published"
            _logger.info(f"Agrupador {self.name} publicado exitosamente")
        else:
            self.state = "draft"

    def _validate_currencies_and_rates(self):
        """Validar que todas las monedas y tasas estén correctamente configuradas"""
        
        # Validar que el diario intermedio tenga moneda
        if not self.account_journal_aggregator_id or not self.account_journal_aggregator_id.currency_id:
            raise ValidationError(_("Intermediate journal must have a currency configured"))
        
        # Validar que la moneda del agrupador coincida con el diario intermedio
        if self.currency_id.id != self.account_journal_aggregator_id.currency_id.id:
            raise ValidationError(_("Payment aggregator currency must match intermediate journal currency"))
        
        # Validar cada método de pago
        for line in self.mps_payment_methods_line_ids:
            # Validar que el diario tenga una moneda definida
            if not line.account_journal_id:
                raise ValidationError(_("Payment method line must have a journal configured"))
            
            # Si el diario no tiene moneda, debe usar la de la empresa
            expected_currency = line.account_journal_id.currency_id or self.env.company.currency_id
            if line.currency_id.id != expected_currency.id:
                raise ValidationError(
                    _("Currency mismatch in payment method line. Expected %s but got %s") % 
                    (expected_currency.name, line.currency_id.name)
                )

    def _reconcile_specific_invoice_amount(self, payment, invoice_move, amount_to_reconcile):
        """
        Método para reconciliar un monto específico entre un pago y una factura
        """
        try:
            # Obtener líneas de pago pendientes de reconciliación
            payment_lines = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] 
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            # Obtener líneas de factura pendientes de reconciliación
            invoice_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] 
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not payment_lines or not invoice_lines:
                _logger.warning(f"No se encontraron líneas para reconciliar: pago {payment.name} con factura {invoice_move.name}")
                return False
                
            # Crear reconciliación usando el API de Odoo
            payment_line = payment_lines[0]
            invoice_line = invoice_lines[0]
            
            # Verificar que hay suficiente saldo residual
            available_payment_amount = abs(payment_line.amount_residual)
            available_invoice_amount = abs(invoice_line.amount_residual)
            
            # Determinar el monto máximo que se puede reconciliar
            max_reconcile_amount = min(available_payment_amount, available_invoice_amount, abs(amount_to_reconcile))
            
            if max_reconcile_amount <= 0.01:  # Monto mínimo significativo
                _logger.warning(f"Monto insuficiente para reconciliar: {max_reconcile_amount}")
                return False
            
            _logger.info(f"Reconciliando {max_reconcile_amount} entre pago {payment.name} y factura {invoice_move.name}")
            
            # Si es reconciliación completa, usar el método estándar
            if (abs(max_reconcile_amount - available_payment_amount) < 0.01 and 
                abs(max_reconcile_amount - available_invoice_amount) < 0.01):
                (invoice_line + payment_line).reconcile()
                return True
            
            # Para reconciliación parcial, crear registro parcial
            try:
                # Determinar las líneas débito y crédito
                debit_line = payment_line if payment_line.debit > 0 else invoice_line
                credit_line = invoice_line if payment_line.debit > 0 else payment_line
                
                # Crear reconciliación parcial
                partial_rec = self.env['account.partial.reconcile'].create({
                    'amount': max_reconcile_amount,
                    'amount_currency': max_reconcile_amount,
                    'currency_id': payment.currency_id.id,
                    'debit_move_id': debit_line.id,
                    'credit_move_id': credit_line.id,
                })
                
                _logger.info(f"Reconciliación parcial creada: {partial_rec.id}")
                return True
                
            except Exception as e:
                _logger.warning(f"Error en reconciliación parcial: {str(e)}. Usando reconciliación completa.")
                (invoice_line + payment_line).reconcile()
                return True
            
        except Exception as e:
            _logger.error(f"Error en reconciliación específica: {str(e)}")
            return False

    def _fix_payment_dates(self, payment, target_date):
        """
        Método MEJORADO para corregir las fechas de los pagos de forma consistente y robusta
        """
        try:
            # Asegurar que target_date es un objeto date
            if isinstance(target_date, str):
                target_date = fields.Date.from_string(target_date)
            elif isinstance(target_date, datetime):
                target_date = target_date.date()
            
            # Actualizar fecha del pago si está en borrador
            if payment.state == 'draft':
                payment.write({'date': target_date})
                _logger.info(f"Fecha del pago actualizada: {payment.name} -> {target_date}")
            else:
                _logger.info(f"Pago {payment.name} ya confirmado, no se puede cambiar fecha directamente")
            
            # Manejar el asiento contable
            if payment.move_id:
                if payment.move_id.state == 'draft':
                    payment.move_id.write({'date': target_date})
                    _logger.info(f"Fecha del asiento actualizada: {payment.move_id.name} -> {target_date}")
                elif payment.move_id.state == 'posted':
                    try:
                        # Solo cambiar fecha si es realmente necesario
                        if payment.move_id.date != target_date:
                            # Regresar a borrador para cambiar fecha
                            payment.move_id.button_draft()
                            payment.move_id.write({'date': target_date})
                            # No re-confirmar aquí, se hará en el flujo principal
                            _logger.info(f"Asiento regresado a borrador y fecha corregida: {payment.move_id.name}")
                    except Exception as move_error:
                        _logger.warning(f"No se pudo cambiar fecha del asiento {payment.move_id.name}: {str(move_error)}")
            
            return True
            
        except Exception as e:
            _logger.error(f"Error corrigiendo fecha del pago {payment.name}: {str(e)}")
            # No lanzar error, solo advertir
            return False

    def _create_mixed_payments(self):
        """
        CASO MIXTO CORREGIDO: Crear pagos individuales por cada factura con el monto exacto asignado
        SIN transferencias internas adicionales
        """
        total_invoice_amount = sum(self.account_move_line_payment_agg_ids.mapped('payment_aggregator_total_import'))
        total_payment_account = self.payment_account or 0
        
        _logger.info(f"=== CREANDO PAGOS MIXTOS ===")
        _logger.info(f"Total facturas: ${total_invoice_amount}")
        _logger.info(f"Pago a cuenta: ${total_payment_account}")
        _logger.info(f"Métodos de pago: {len(self.mps_payment_methods_line_ids)}")
        
        payments_created = []
        
        # PASO 1: Crear un pago específico por cada factura con su monto exacto
        for credit_line in self.account_move_line_payment_agg_ids:
            if credit_line.payment_aggregator_total_import > 0:
                assigned_amount = credit_line.payment_aggregator_total_import
                _logger.info(f"Creando pago para factura {credit_line.move_id.name}: ${assigned_amount}")
                
                # Usar el primer método de pago disponible como referencia
                payment_method = self.mps_payment_methods_line_ids[0] if self.mps_payment_methods_line_ids else None
                if not payment_method:
                    raise UserError("No hay métodos de pago disponibles")
                
                # USAR EL DIARIO DEL MÉTODO DE PAGO DIRECTAMENTE, NO EL INTERMEDIO
                journal = payment_method.account_journal_id
                
                # Buscar método de pago apropiado
                if self.receiptbook_id.type == "inbound":
                    method_line = journal.inbound_payment_method_line_ids.filtered(
                        lambda m: m.id == payment_method.payment_method_line_id.id
                    )[:1]
                    if not method_line:
                        method_line = journal.inbound_payment_method_line_ids.filtered(
                            lambda m: m.payment_method_id.code == 'manual'
                        )[:1] or journal.inbound_payment_method_line_ids[:1]
                    payment_type = 'inbound'
                else:
                    method_line = journal.outbound_payment_method_line_ids.filtered(
                        lambda m: m.id == payment_method.payment_method_line_id.id
                    )[:1]
                    if not method_line:
                        method_line = journal.outbound_payment_method_line_ids.filtered(
                            lambda m: m.payment_method_id.code == 'manual'
                        )[:1] or journal.outbound_payment_method_line_ids[:1]
                    payment_type = 'outbound'
                
                # CREAR PAGO DIRECTO EN EL DIARIO DEL MÉTODO (SIN DIARIO INTERMEDIO)
                payment_vals = {
                    'payment_type': payment_type,
                    'partner_type': self.receiptbook_id.partner_type,
                    'partner_id': self.customer_id.id,
                    'amount': assigned_amount,  # MONTO EXACTO ASIGNADO
                    'currency_id': payment_method.currency_id.id,  # MONEDA DEL MÉTODO
                    'date': payment_method.date or self.date,
                    'ref': f'Invoice Payment: {credit_line.move_id.name} - {self.name}',
                    'journal_id': journal.id,  # DIARIO DEL MÉTODO DIRECTAMENTE
                    'payment_method_line_id': method_line.id,
                    'is_internal_transfer': False,
                    'payment_aggregator_id': self.id,
                }
                
                # Agregar campos de cheque si aplica
                if payment_method.is_check:
                    payment_vals.update({
                        'l10n_latam_check_number': payment_method.check_number,
                        'l10n_latam_check_payment_date': payment_method.check_cash_date,
                        'l10n_latam_check_bank_id': payment_method.check_bank_id.id,
                        'l10n_latam_check_issuer_vat': payment_method.check_vat,
                    })
                
                # CREAR Y CONFIRMAR EL PAGO
                payment = self.env['account.payment'].create(payment_vals)
                
                try:
                    payment.action_post()
                    if payment.state != 'posted':
                        payment.move_id._post(soft=False)
                        payment.write({'state': 'posted'})
                    
                    _logger.info(f"✓ Pago para factura creado: {payment.name} - ${payment.amount}")
                    
                    # RECONCILIAR DIRECTAMENTE ESTA FACTURA CON ESTE PAGO
                    payment_lines = payment.line_ids.filtered(
                        lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] 
                        and not line.reconciled
                    )
                    invoice_lines = credit_line.move_id.line_ids.filtered(
                        lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] 
                        and not line.reconciled
                    )
                    
                    if payment_lines and invoice_lines:
                        (invoice_lines + payment_lines).reconcile()
                        _logger.info(f"✓ Factura {credit_line.move_id.name} reconciliada con pago {payment.name}")
                        
                        # Actualizar estado de la factura
                        credit_line.move_id._compute_payment_state()
                    
                    payments_created.append(payment)
                    
                except Exception as e:
                    _logger.error(f"Error procesando pago para factura {credit_line.move_id.name}: {str(e)}")
                    raise UserError(f"Error creando pago para factura {credit_line.move_id.name}: {str(e)}")
        
        # PASO 2: Crear pago a cuenta si aplica (también directo, sin intermedio)
        if total_payment_account > 0:
            self._create_payment_account_direct()
        
        # NO CREAR TRANSFERENCIAS ADICIONALES EN CASOS MIXTOS
        # Los pagos ya se crearon directamente en los diarios correspondientes
        
        _logger.info(f"=== PAGOS MIXTOS COMPLETADOS ===")
        _logger.info(f"Pagos de facturas creados: {len(payments_created)}")
        _logger.info("NOTA: No se crearon transferencias internas adicionales (pagos directos)")
        return payments_created

    def _create_payment_account_direct(self):
        """
        Crear pago a cuenta DIRECTO en el diario del método de pago (sin intermedio)
        """
        if self.payment_account <= 0:
            return
            
        _logger.info(f"Creando pago a cuenta DIRECTO: ${self.payment_account}")
        
        # Usar el primer método de pago como referencia
        payment_method = self.mps_payment_methods_line_ids[0] if self.mps_payment_methods_line_ids else None
        if not payment_method:
            raise UserError("No hay métodos de pago disponibles para pago a cuenta")
        
        journal = payment_method.account_journal_id
        
        # Buscar método de pago apropiado
        if self.receiptbook_id.type == "inbound":
            method_line = journal.inbound_payment_method_line_ids.filtered(
                lambda m: m.payment_method_id.code == 'manual'
            )[:1] or journal.inbound_payment_method_line_ids[:1]
            payment_type = 'inbound'
        else:
            method_line = journal.outbound_payment_method_line_ids.filtered(
                lambda m: m.payment_method_id.code == 'manual'
            )[:1] or journal.outbound_payment_method_line_ids[:1]
            payment_type = 'outbound'
        
        payment_vals = {
            'payment_type': payment_type,
            'partner_type': self.receiptbook_id.partner_type,
            'partner_id': self.customer_id.id,
            'amount': self.payment_account,
            'currency_id': payment_method.currency_id.id,
            'date': payment_method.date or self.date,
            'ref': f'Payment on Account: {self.name}',
            'journal_id': journal.id,  # DIARIO DIRECTO, NO INTERMEDIO
            'payment_method_line_id': method_line.id,
            'is_internal_transfer': False,
            'payment_aggregator_id': self.id,
        }
        
        try:
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()
            if payment.state != 'posted':
                payment.move_id._post(soft=False)
                payment.write({'state': 'posted'})
            
            _logger.info(f"✓ Pago a cuenta DIRECTO creado: {payment.name} - ${payment.amount}")
            
        except Exception as e:
            _logger.error(f"Error creando pago a cuenta directo: {str(e)}")
            raise UserError(f"Error creando pago a cuenta directo: {str(e)}")

    def _create_payment_account_simple(self):
        """
        Crear pago a cuenta simple en diario intermedio
        """
        if self.payment_account <= 0:
            return
            
        _logger.info(f"Creando pago a cuenta: ${self.payment_account}")
        
        # Usar diario intermedio
        if self.receiptbook_id.type == "inbound":
            method_line = self.account_journal_aggregator_id.account_journal_id.inbound_payment_method_line_ids.filtered(
                lambda m: m.payment_method_id.code == 'manual'
            )[:1] or self.account_journal_aggregator_id.account_journal_id.inbound_payment_method_line_ids[:1]
            payment_type = 'inbound'
        else:
            method_line = self.account_journal_aggregator_id.account_journal_id.outbound_payment_method_line_ids.filtered(
                lambda m: m.payment_method_id.code == 'manual'
            )[:1] or self.account_journal_aggregator_id.account_journal_id.outbound_payment_method_line_ids[:1]
            payment_type = 'outbound'
        
        payment_vals = {
            'payment_type': payment_type,
            'partner_type': self.receiptbook_id.partner_type,
            'partner_id': self.customer_id.id,
            'amount': self.payment_account,
            'currency_id': self.currency_id.id,
            'date': self.date,
            'ref': f'Payment on Account: {self.name}',
            'journal_id': self.account_journal_aggregator_id.account_journal_id.id,
            'payment_method_line_id': method_line.id,
            'is_internal_transfer': False,
            'payment_aggregator_id': self.id,
        }
        
        try:
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()
            if payment.state != 'posted':
                payment.move_id._post(soft=False)
                payment.write({'state': 'posted'})
            
            _logger.info(f"✓ Pago a cuenta creado: {payment.name} - ${payment.amount}")
            
        except Exception as e:
            _logger.error(f"Error creando pago a cuenta: {str(e)}")
            raise UserError(f"Error creando pago a cuenta: {str(e)}")

    def _create_payment_method_transfers(self):
        """
        Crear transferencias internas desde diario intermedio hacia los métodos de pago específicos
        """
        _logger.info("Creando transferencias a métodos de pago específicos")
        
        for payment_method in self.mps_payment_methods_line_ids:
            journal = payment_method.account_journal_id
            if not journal:
                continue
                
            try:
                # CREAR TRANSFERENCIA INTERNA
                payment_details = {
                    'payment_type': payment_method.payment_type,
                    'partner_id': self.customer_id.id,
                    'amount': payment_method.amount,  # Monto en moneda del agrupador
                    'currency_id': payment_method.currency_id.id,  # Moneda del método
                    'date': payment_method.date or self.date,
                    'ref': f'Transfer to {journal.name}: {self.name}',
                    'journal_id': journal.id,  # Diario destino
                    'destination_journal_id': self.account_journal_aggregator_id.account_journal_id.id,  # Diario origen
                    'is_internal_transfer': True,
                    'payment_aggregator_id': self.id,
                }
                
                # Buscar método de pago para la transferencia
                if payment_method.payment_type == "inbound":
                    method_line = journal.inbound_payment_method_line_ids.filtered(
                        lambda m: m.id == payment_method.payment_method_line_id.id
                    )[:1] or journal.inbound_payment_method_line_ids[:1]
                else:
                    method_line = journal.outbound_payment_method_line_ids.filtered(
                        lambda m: m.id == payment_method.payment_method_line_id.id
                    )[:1] or journal.outbound_payment_method_line_ids[:1]
                
                if method_line:
                    payment_details['payment_method_line_id'] = method_line.id
                
                # Agregar campos de cheque si aplica
                if payment_method.is_check:
                    payment_details.update({
                        'l10n_latam_check_number': payment_method.check_number,
                        'l10n_latam_check_payment_date': payment_method.check_cash_date,
                        'l10n_latam_check_bank_id': payment_method.check_bank_id.id,
                        'l10n_latam_check_issuer_vat': payment_method.check_vat,
                    })
                
                # Crear transferencia
                transfer = self.env['account.payment'].create(payment_details)
                transfer.action_post()
                
                if transfer.state != 'posted':
                    transfer.move_id._post(soft=False)
                    transfer.write({'state': 'posted'})
                
                # Crear transferencia espejo si no se creó automáticamente
                if not transfer.paired_internal_transfer_payment_id:
                    transfer._create_paired_internal_transfer_payment()
                
                _logger.info(f"✓ Transferencia creada: {transfer.name} - ${transfer.amount}")
                
            except Exception as e:
                _logger.error(f"Error creando transferencia para {journal.name}: {str(e)}")
                # No fallar completamente, solo advertir
                continue

    def _reconcile_invoices_with_mixed_payments(self, payments_created):
        """
        Reconciliar facturas con los pagos mixtos creados con distribución proporcional correcta
        """
        _logger.info("Iniciando reconciliación CORREGIDA de facturas con pagos mixtos")
        
        if not payments_created:
            _logger.warning("No se encontraron pagos confirmados para reconciliar")
            return
        
        # Agrupar facturas por el monto específico asignado
        invoices_to_reconcile = []
        total_assigned_amount = 0
        
        for credit_line in self.account_move_line_payment_agg_ids:
            if credit_line.payment_aggregator_total_import > 0:
                invoice_data = {
                    'invoice': credit_line.move_id,
                    'assigned_amount': credit_line.payment_aggregator_total_import,
                    'remaining_amount': credit_line.payment_aggregator_total_import,
                    'credit_line': credit_line
                }
                invoices_to_reconcile.append(invoice_data)
                total_assigned_amount += credit_line.payment_aggregator_total_import
        
        if not invoices_to_reconcile:
            _logger.info("No hay facturas con montos asignados para reconciliar")
            return
        
        _logger.info(f"Total asignado a facturas: ${total_assigned_amount}")
        _logger.info(f"Facturas a reconciliar: {[inv['invoice'].name for inv in invoices_to_reconcile]}")
        
        # Distribuir cada pago proporcionalmente entre todas las facturas
        for payment in payments_created:
            payment_amount_remaining = payment.amount
            _logger.info(f"Procesando pago {payment.name} por ${payment_amount_remaining}")
            
            for invoice_data in invoices_to_reconcile:
                if payment_amount_remaining <= 0.01:  # Monto mínimo
                    break
                
                if invoice_data['remaining_amount'] <= 0.01:
                    continue  # Ya se asignó todo a esta factura
                
                invoice = invoice_data['invoice']
                
                # Calcular proporción de este pago que corresponde a esta factura
                if total_assigned_amount > 0:
                    proportion = invoice_data['assigned_amount'] / total_assigned_amount
                else:
                    proportion = 1.0 / len(invoices_to_reconcile)  # Distribuir equitativamente
                
                amount_for_this_invoice = payment.amount * proportion
                
                # No exceder el monto restante asignado a la factura ni el monto restante del pago
                final_amount = min(
                    amount_for_this_invoice, 
                    invoice_data['remaining_amount'],
                    payment_amount_remaining
                )
                
                if final_amount > 0.01:  # Solo procesar si hay monto significativo
                    _logger.info(f"Asignando ${final_amount} del pago {payment.name} a factura {invoice.name}")
                    
                    # Reconciliar el monto específico
                    success = self._reconcile_specific_invoice_amount(
                        payment, 
                        invoice, 
                        final_amount
                    )
                    
                    if success:
                        payment_amount_remaining -= final_amount
                        invoice_data['remaining_amount'] -= final_amount
                        
                        # Actualizar estado de la factura
                        invoice._compute_payment_state()
                        
                        _logger.info(f"Reconciliado exitosamente: ${final_amount} - Restante del pago: ${payment_amount_remaining}")

    def _create_payment_account_if_needed_with_invoices(self):
        """
        Para casos con facturas: crear pago a cuenta en diario intermedio
        """
        if self.payment_account > 0:
            payment_details = self._get_standard_payment()
            payment_details['amount'] = self.payment_account
            payment_details['ref'] = f'Payment on account: {self.name}'

            if self.receiptbook_id.type == "inbound":
                payment_method_line = self.account_journal_aggregator_id.account_journal_id.inbound_payment_method_line_ids.filtered(
                    lambda pay: pay.payment_method_id.id == self.env.ref("account.account_payment_method_manual_in").id
                )
            else:
                payment_method_line = self.account_journal_aggregator_id.account_journal_id.outbound_payment_method_line_ids.filtered(
                    lambda pay: pay.payment_method_id.id == self.env.ref("account.account_payment_method_manual_out").id
                )
            
            payment_details["payment_method_line_id"] = payment_method_line.id
            payment_details["payment_method_id"] = payment_method_line.payment_method_id.id

            payment = self.create_publish_payment(payment_details)
            payment.set_transaction_type()
            
            # CORREGIR FECHA
            self._fix_payment_dates(payment, self.date)
            
            payment.action_post()
            
            _logger.info(f"Pago a cuenta con facturas creado: {self.payment_account}")

    def _create_lines_payment_payments_v2(self):
        """
        Método CORREGIDO para pagos a cuenta puros (sin facturas)
        Crea pagos DIRECTOS en los diarios de métodos, SIN transferencias internas
        """
        _logger.info("=== CREANDO PAGOS A CUENTA PUROS (SIN FACTURAS) ===")
        
        for payment_method in self.mps_payment_methods_line_ids:
            journal = payment_method.account_journal_id
            
            if not journal:
                raise UserError(_("La linea de pago debe contener un diario contable"))
            
            try:
                # Buscar método de pago apropiado para el diario ORIGINAL
                if self.receiptbook_id.type == "inbound":
                    method_line = journal.inbound_payment_method_line_ids.filtered(
                        lambda m: m.id == payment_method.payment_method_line_id.id
                    )[:1]
                    if not method_line:
                        method_line = journal.inbound_payment_method_line_ids.filtered(
                            lambda m: m.payment_method_id.code == 'manual'
                        )[:1] or journal.inbound_payment_method_line_ids[:1]
                    payment_type = 'inbound'
                else:
                    method_line = journal.outbound_payment_method_line_ids.filtered(
                        lambda m: m.id == payment_method.payment_method_line_id.id
                    )[:1]
                    if not method_line:
                        method_line = journal.outbound_payment_method_line_ids.filtered(
                            lambda m: m.payment_method_id.code == 'manual'
                        )[:1] or journal.outbound_payment_method_line_ids[:1]
                    payment_type = 'outbound'
                
                if not method_line:
                    raise UserError(f"No hay métodos de pago disponibles para el diario {journal.name}")
                
                # USAR FECHA ESPECÍFICA DEL MÉTODO
                payment_date = payment_method.date or self.date
                
                # CREAR PAGO DIRECTO EN EL DIARIO DEL MÉTODO (NO TRANSFERENCIA INTERNA)
                payment_vals = {
                    'payment_type': payment_type,
                    'partner_type': self.receiptbook_id.partner_type,
                    'partner_id': self.customer_id.id,
                    'amount': payment_method.payment_amount,  # MONTO ORIGINAL EN MONEDA ORIGINAL
                    'currency_id': payment_method.currency_id.id,  # MONEDA ORIGINAL
                    'date': payment_date,  # FECHA ESPECÍFICA
                    'ref': f'Payment on Account: {self.name} - {journal.name}',
                    'journal_id': journal.id,  # DIARIO ORIGINAL (NO INTERMEDIO)
                    'payment_method_line_id': method_line.id,
                    'is_internal_transfer': False,  # PAGO DIRECTO, NO TRANSFERENCIA
                    'payment_aggregator_id': self.id,
                }
                
                # CAMPOS DE CHEQUES - TODOS los datos del cheque
                if payment_method.is_check:
                    payment_vals.update({
                        'l10n_latam_check_number': payment_method.check_number,
                        'l10n_latam_check_payment_date': payment_method.check_cash_date,
                        'l10n_latam_check_bank_id': payment_method.check_bank_id.id,
                        'l10n_latam_check_issuer_vat': payment_method.check_vat,
                        'l10n_latam_check_current_journal_id': journal.id,
                    })
                
                # CREAR PAGO DIRECTO
                payment = self.env['account.payment'].create(payment_vals)
                _logger.info(f"Pago a cuenta creado en borrador: {payment.name} - Estado: {payment.state}")
                
                # VALIDAR QUE EL PAGO SE CREÓ CORRECTAMENTE
                if not payment or not payment.move_id:
                    raise UserError(f"Error: No se pudo crear el pago o su asiento contable para {journal.name}")
                
                # CORREGIR FECHAS ANTES DE CONFIRMAR
                self._fix_payment_dates(payment, payment_date)
                
                # CORREGIR ASIENTO CONTABLE ANTES DE PUBLICAR
                if payment.move_id and payment.move_id.state == 'draft':
                    self._fix_payment_move_currencies(
                        payment, 
                        payment_method.payment_amount,
                        payment_method.amount,
                        payment_method
                    )
                
                # CONFIRMAR EL PAGO CON MANEJO DE ERRORES ROBUSTO
                try:
                    _logger.info(f"Intentando confirmar pago a cuenta {payment.name}...")
                    payment.action_post()
                    
                    # VERIFICAR QUE SE CONFIRMÓ CORRECTAMENTE
                    if payment.state != 'posted':
                        _logger.warning(f"El pago {payment.name} no se confirmó correctamente. Estado actual: {payment.state}")
                        # Intentar confirmar manualmente
                        if payment.move_id and payment.move_id.state == 'draft':
                            payment.move_id._post(soft=False)
                        payment.write({'state': 'posted'})
                    
                    _logger.info(f"Pago a cuenta confirmado exitosamente: {payment.name} - Estado: {payment.state}")
                    
                except Exception as post_error:
                    _logger.error(f"Error confirmando pago a cuenta {payment.name}: {str(post_error)}")
                    # Si falla la confirmación automática, intentar confirmación manual
                    try:
                        if payment.move_id and payment.move_id.state == 'draft':
                            payment.move_id._post(soft=False)
                        payment.write({'state': 'posted'})
                        _logger.info(f"Pago a cuenta confirmado manualmente: {payment.name}")
                    except Exception as manual_error:
                        _logger.error(f"Error en confirmación manual: {str(manual_error)}")
                        raise UserError(f"No se pudo confirmar el pago a cuenta {payment.name}: {str(manual_error)}")
                
                # ASEGURAR FECHAS DESPUÉS DE CONFIRMAR
                self._fix_payment_dates(payment, payment_date)
                
                if payment.move_id:
                    payment.move_id.line_ids.write({'payment_aggregator_id': self.id})
                
                _logger.info(f"✓ Pago a cuenta DIRECTO creado: {payment.name} - {payment.amount} {payment.currency_id.name} - Estado: {payment.state} - Fecha: {payment.date}")
                
            except Exception as e:
                error_msg = f"Error creando pago a cuenta para {journal.name}: {str(e)}"
                _logger.error(error_msg)
                raise UserError(error_msg)
        
        _logger.info("=== PAGOS A CUENTA PUROS COMPLETADOS ===")
        _logger.info("NOTA: Se crearon pagos DIRECTOS, sin transferencias internas")

    def _fix_payment_move_currencies(self, payment, amount_in_payment_currency, amount_in_aggregator_currency, payment_method):
        """
        Corregir los asientos contables para manejar correctamente las monedas
        """
        if not payment.move_id or payment.move_id.state != 'draft':
            return
        
        company_currency = self.env.company.currency_id
        payment_currency = payment_method.currency_id
        
        # Calcular el monto en moneda de la empresa
        date = payment.date or fields.Date.today()
        
        if payment_currency.id == company_currency.id:
            amount_company_currency = amount_in_payment_currency
        else:
            # Convertir de moneda de pago a moneda de empresa
            amount_company_currency = payment_currency._convert(
                amount_in_payment_currency,
                company_currency,
                self.env.company,
                date
            )
        
        line_ids = []
        for line in payment.move_id.line_ids:
            vals = {}
            
            # Establecer la moneda de la línea si es diferente a la de la empresa
            if payment_currency.id != company_currency.id:
                vals['currency_id'] = payment_currency.id
            
            if line.debit > 0:
                vals.update({
                    'debit': amount_company_currency,
                    'balance': amount_company_currency,
                })
                
                # Si hay moneda extranjera, establecer amount_currency
                if payment_currency.id != company_currency.id:
                    vals['amount_currency'] = amount_in_payment_currency
                    
            elif line.credit > 0:
                vals.update({
                    'credit': amount_company_currency,
                    'balance': -amount_company_currency,
                })
                
                # Si hay moneda extranjera, establecer amount_currency
                if payment_currency.id != company_currency.id:
                    vals['amount_currency'] = -amount_in_payment_currency
            
            # Solo actualizar si hay cambios
            if vals:
                line_ids.append((1, line.id, vals))
        
        # Aplicar los cambios
        if line_ids:
            payment.move_id.write({'line_ids': line_ids})
        
        _logger.info("Corregido asiento contable del pago %s: payment_currency=%.2f, company_currency=%.2f", 
                     payment.name, amount_in_payment_currency, amount_company_currency)

    # MÉTODOS ORIGINALES MANTENIDOS (con correcciones menores de fechas)
    def _create_lines_payment_payments(self):
        # Líneas de pago
        for payment_method in self.mps_payment_methods_line_ids:
            # Tomamos el diario de la línea de pago
            journal = payment_method.account_journal_id
            
            # Validamos
            if not journal:
                raise UserError(_("La linea de pago debe contener un diario contable"))
            
            # USAR FECHA ESPECÍFICA DEL MÉTODO
            payment_date = payment_method.date or self.date
            
            # Construimos el diccionario para el pago
            payment_details = self._get_standard_payment()
            payment_details['date'] = payment_date
            payment_details['date_mps'] = payment_date
            payment_details['amount'] = payment_method["amount"]
            payment_details['amount_destino'] = payment_method["amount"]
            payment_details['payment_type'] = payment_method["payment_type"]
            payment_details['payment_type_mps'] = payment_method["payment_type"]
            payment_details['is_internal_transfer'] = True   # Marcamos
            payment_details['is_internal_transfer_mps'] = True   # Marcamos
            payment_details['ref'] = _('Internal Transfer')   # Referencia
            payment_details['payment_method_line_id'] = payment_method["payment_method_line_id"]["id"]
            payment_details['payment_method_id'] = payment_method["payment_method_line_id"]["payment_method_id"]["id"]
            payment_details['transaction_type'] = "internal_transfer"
            payment_details['currency_id'] = payment_method.currency_id.id
            
            if payment_method["is_check"]:
                payment_details['l10n_latam_check_number'] = payment_method["check_number"]
                payment_details['l10n_latam_check_payment_date'] = payment_method["check_cash_date"]
                payment_details['l10n_latam_check_bank_id'] = payment_method["check_bank_id"]["id"]
                payment_details['l10n_latam_check_issuer_vat'] = payment_method["check_vat"]
                payment_details['l10n_latam_check_current_journal_id'] = journal.id

            # Validar el sentido del talonario para registrar el pago
            if self.receiptbook_id.type == "outbound":
                payment_details['journal_id'] = journal.id
                payment_details['destination_journal_id'] = self.account_journal_aggregator_id.account_journal_id.id,
            else:
                payment_details['journal_id'] = journal.id
                payment_details['destination_journal_id'] = self.account_journal_aggregator_id.account_journal_id.id,
            
            # Creamos el pago
            payment = self.create_publish_payment(payment_details)

            # Modificación de asientos con fechas correctas
            amount = payment_method["amount"]

            self._setDebitCreditAmount(
                payment=payment, 
                amount_in_payment_currency=payment_method["payment_amount"],
                amount_in_aggregator_currency=amount,
                payment_method=payment_method
            )

            # CORREGIR FECHAS
            self._fix_payment_dates(payment, payment_date)
            
            # Publicamos el asiento
            payment.move_id._post(soft=False)
            payment._create_paired_internal_transfer_payment()

            payment.paired_internal_transfer_payment_id.write({
                "payment_type_mps":"inbound" if payment_method["payment_type"] == "outbound" else "outbound",
                "date_mps": payment_date,
                "date": payment_date,
            })
            
            # CORREGIR FECHAS EN TRANSFERENCIA ESPEJO
            self._fix_payment_dates(payment.paired_internal_transfer_payment_id, payment_date)

            check_id = False

            if payment_method["is_check"] == False:
                self.env.cr.execute("UPDATE account_payment SET is_internal_transfer = %s, partner_id = '%s' WHERE id = %s;" % (True, self.customer_id.id, int(payment.id)))
            else:
                # Creamos el cheque con fecha correcta
                check_id = self.env["account.payment"].create({
                    "payment_type": payment_method["payment_type"],
                    "partner_id": self.customer_id.id,
                    "amount": payment_method["payment_amount"],
                    "amount_destino": payment_method["payment_amount"],
                    "date": payment_date,  # FECHA CORRECTA
                    "date_mps": payment_date,
                    "journal_id": journal.id,
                    "payment_method_line_id": payment_method["payment_method_line_id"]["id"],
                    "l10n_latam_check_number": payment_method["check_number"],
                    "l10n_latam_check_payment_date": payment_method["check_cash_date"],
                    "l10n_latam_check_bank_id": payment_method["check_bank_id"]["id"],
                    "l10n_latam_check_issuer_vat": payment_method["check_vat"],
                    "l10n_latam_check_current_journal_id": self.account_journal_aggregator_id.account_journal_id.id,
                    "is_internal_transfer": False
                })

                check_id.write({
                    "l10n_latam_check_bank_id": payment_method["check_bank_id"]["id"],
                })

                check_id.action_post()

                payment.write({
                    "l10n_latam_check_mps_id": check_id.id
                })

            # Resto del código de transferencias internas igual...
            mirror_payment = payment.paired_internal_transfer_payment_id

            if payment_method["is_check"] == False:
                self.env.cr.execute("UPDATE account_payment SET is_internal_transfer = %s, partner_id = %s, payment_type = '%s' WHERE paired_internal_transfer_payment_id = %s;" % (
                        True, 
                        self.customer_id.id, 
                        "inbound" if payment_method["payment_type"] == "outbound" else "outbound", 
                        int(payment.id)
                    )
                )
            else:
                self.env.cr.execute(
                    "UPDATE account_payment " \
                    "SET is_internal_transfer = %s, " \
                    "partner_id = %s, " \
                    "l10n_latam_check_id = %s " \
                    "WHERE paired_internal_transfer_payment_id = %s;" % (True, self.customer_id.id, check_id.id, int(payment.id)))

            mirror_payment.move_id.button_draft()

            self._setDebitCreditAmount(
                payment=mirror_payment, 
                amount_in_payment_currency=payment_method["payment_amount"],
                amount_in_aggregator_currency=amount,
                payment_method=payment_method,
                is_mirror=True
            )
            
            mirror_payment._multiple_payments_action_post()

    def _create_payment_acount(self):
        if self.payment_account > 0:
            payment_details = self._get_standard_payment()
            payment_details['amount'] = self.payment_account

            if self.receiptbook_id.type == "inbound":
                payment_method_line = self.account_journal_aggregator_id.account_journal_id.inbound_payment_method_line_ids.filtered(
                    lambda pay: pay.payment_method_id.id == self.env.ref("account.account_payment_method_manual_in").id
                )
            else:
                payment_method_line = self.account_journal_aggregator_id.account_journal_id.outbound_payment_method_line_ids.filtered(
                    lambda pay: pay.payment_method_id.id == self.env.ref("account.account_payment_method_manual_out").id
                )
            
            payment_details["payment_method_line_id"] = payment_method_line.id
            payment_details["payment_method_id"] = payment_method_line.payment_method_id.id

            payment = self.create_publish_payment(payment_details)
            payment.set_transaction_type()
            
            # CORREGIR FECHAS
            self._fix_payment_dates(payment, self.date)
            
            payment.action_post()

    def _create_invoices_payment(self):
        if self.account_move_line_payment_agg_ids:
            self._delete_accounting_notes()

            if len(self.account_move_line_payment_agg_ids) > 0:
                for credit_line in self.account_move_line_payment_agg_ids:
                    payment_details = self._get_standard_payment()
                    payment_details["amount"] = credit_line.payment_aggregator_total_import
                    payment_details["ref"] = credit_line.move_id.name

                    move_id = self.create_publish_payment(payment_details)

                    # CORREGIR FECHAS
                    self._fix_payment_dates(move_id, self.date)

                    move_id.set_transaction_type()
                    move_id.action_post()
                    move_id._compute_reconciliation_status()

                    # Reconciliación igual que antes
                    payment_lines = move_id.line_ids.filtered(
                        lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
                    )
                    invoice_lines = credit_line.move_id.line_ids.filtered(
                        lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
                    )
                    (invoice_lines + payment_lines).reconcile()

                    for payment_line in payment_lines:
                        if payment_line.move_id.payment_id:
                            payment_line.move_id.payment_id.is_matched = True

                    credit_line.move_id._compute_payment_state()

    # RESTO DE MÉTODOS IGUALES
    def _get_standard_payment(self):
        return {
            'partner_id': self.customer_id.id,
            "partner_mps_id": self.customer_id.id,
            'date': self.date,
            "date_mps": self.date,
            'amount': 0,
            'is_internal_transfer': False,
            'payment_type': self.receiptbook_id.type,
            'payment_type_mps': self.receiptbook_id.type,
            'journal_id': self.account_journal_aggregator_id.account_journal_id.id,
            'partner_type': self.receiptbook_id.partner_type,
            'payment_aggregator_id': self.id
        }
    
    def create_publish_payment(self, payment_details):
        if not payment_details:
            raise ValidationError(_("Payments cannot be created with empty information."))
        if "destination_journal_id" in payment_details:
            payment_details["currency_destino_id"] = payment_details["destination_journal_id"][0]
        payment_id = self.env['account.payment'].create(payment_details)
        payment_id.line_ids.payment_aggregator_id = self.id
        return payment_id

    @api.depends('amount', 'payment_account', 'debt_allocation')
    def _compute_difference(self):
        for record in self:
            record.difference = record.amount - (record.payment_account + record.debt_allocation)

    @api.depends('account_move_line_payment_agg_ids.payment_aggregator_total_import')
    def _compute_debt_allocation(self):
        for record in self:
            record.debt_allocation = sum(record.account_move_line_payment_agg_ids.mapped('payment_aggregator_total_import'))
            for credit_line, agg_line in zip(record.mps_credits_line_ids, record.account_move_line_payment_agg_ids):
                credit_line.total_import = agg_line.payment_aggregator_total_import
    
    @api.onchange('customer_id', 'currency_id')
    def filter_credit_moves(self):
        self.mps_credits_line_ids = self.search_account_move_line()
        self.set_account_move_line(self.mps_credits_line_ids)

        if self.currency_id:
            intermediate_diary = self.env["account.journal.aggregator"].search([
                ('company_id','=',self.env.company.id),
                ('currency_id','=',self.currency_id.id)
            ], limit=1)
            if intermediate_diary:
                self.account_journal_aggregator_id = intermediate_diary.id

    def assign_domain(self, payment_state='not_paid'):
        return [
            ('partner_id', '=', self.customer_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']), 
            ('move_id.move_type', 'in', ['out_invoice','in_invoice']),
            ('move_id.state','=','posted')
        ]
    
    def search_account_move_line(self):
        return self.env['account.move.line'].search(self.assign_domain())
    
    def set_account_move_line(self, credit_lines=False):
        aggregator_ids = []
        if credit_lines:
            for credit_line in credit_lines:
                if credit_line.amount_residual != 0 and credit_line.parent_state != 'cancel':
                    aggregator_record = self.env['account.move.line.payment.aggregator'].create({
                        'account_move_line_id': credit_line.id,
                        'move_id': credit_line.move_id.id,
                        'payment_aggregator_amount_currency': credit_line.amount_currency,
                        'payment_aggregator_amount_residual': credit_line.amount_residual_currency
                    })
                    aggregator_ids.append(aggregator_record.id if aggregator_record.id else aggregator_record.origin)
        self.account_move_line_payment_agg_ids = [(6, 0, aggregator_ids)]
    
    def button_open_accounting_notes(self):
        self.ensure_one()
        move_ids = self.env['account.move.line'].search([('payment_aggregator_id', '=', self.id)])
        return {
            'name': 'Asientos Contables',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', move_ids.ids)],
            'context': {'group_by': ['journal_id']},
        }
    
    def button_open_grouped_payments(self):
        self.ensure_one()
        return {
            'name': 'Pagos Agrupados',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            "views": [(self.env.ref('multiple_payments.account_payment_multiple_payments_group_view_tree').id, "tree"),(self.env.ref("account.view_account_payment_form").id, "form")],
            'context': {'group_by': ['transaction_type']},
            'domain': [('payment_aggregator_id', '=', self.id)]
        }
    
    def button_update_accounting_notes(self):
        self.filter_credit_moves()
        return
    
    def button_delete_accounting_notes(self):
        self._delete_accounting_notes()
        return
    
    def _delete_accounting_notes(self):
        lines_to_remove = self.account_move_line_payment_agg_ids.filtered(lambda line: line.payment_aggregator_total_import == 0)
        self.write({'account_move_line_payment_agg_ids': [(3, line.id) for line in lines_to_remove]})
        return True

    def button_apply_fifo(self):
        if self.difference > 0 and self.account_move_line_payment_agg_ids:
            sorted_moves = self.account_move_line_payment_agg_ids.sorted(key=lambda r: r.date or fields.Date.today())
            
            for move in sorted_moves:
                if move.payment_aggregator_total_import == 0:
                    total_import = abs(move.credit) + abs(move.debit)
                    if total_import <= 0:
                        continue
                    if (self.difference - total_import) >= 0:
                        move.payment_aggregator_total_import = total_import
                    else:
                        break

    def button_assign_all(self):
        for record in self.account_move_line_payment_agg_ids:
            if record.payment_aggregator_total_import == 0:
                total_import = record.credit + record.debit
                if (self.difference - total_import) >= 0:
                    record.payment_aggregator_total_import = total_import
        return
    
    @api.model
    def create(self, values):
        values['company_id'] = self.env.company.id
        result = super().create(values)
        result.name = self.env['ir.sequence'].next_by_code('aggregator.sequence')
        return result
    
    @api.onchange('receiptbook_id')
    def _validate_recieptbook (self):
        if self.receiptbook_id.partner_type:
            if str(self.receiptbook_id.partner_type) not in self.domain_receiptbook_id:
                raise ValidationError(_(f'You cannot set a {self.receiptbook_id.partner_type.capitalize()} reciept type in this payment aggregator'))

    def _setDebitCreditAmount(self, payment, amount_in_payment_currency, amount_in_aggregator_currency, payment_method, is_mirror=False):
        """
        Método corregido para manejar correctamente las monedas en los asientos contables
        """
        company_currency = self.env.company.currency_id
        payment_currency = payment_method.currency_id
        
        # Calcular el monto en moneda de la empresa
        date = payment.date or fields.Date.today()
        
        if payment_currency.id == company_currency.id:
            amount_company_currency = amount_in_payment_currency
        else:
            amount_company_currency = payment_currency._convert(
                amount_in_payment_currency,
                company_currency,
                self.env.company,
                date
            )
        
        line_ids = []
        for line in payment.move_id.line_ids:
            vals = {}
            
            if payment_currency.id != company_currency.id:
                vals['currency_id'] = payment_currency.id
            
            if line.debit > 0:
                vals.update({
                    'debit': amount_company_currency,
                    'balance': amount_company_currency,
                })
                
                if payment_currency.id != company_currency.id:
                    vals['amount_currency'] = amount_in_payment_currency
                    
            elif line.credit > 0:
                vals.update({
                    'credit': amount_company_currency,
                    'balance': -amount_company_currency,
                })
                
                if payment_currency.id != company_currency.id:
                    vals['amount_currency'] = -amount_in_payment_currency
            
            if vals:
                line_ids.append((1, line.id, vals))
        
        if line_ids:
            payment.move_id.write({'line_ids': line_ids})
        
        _logger.info("Updated payment %s with amounts: payment_currency=%.2f, company_currency=%.2f", 
                     payment.name, amount_in_payment_currency, amount_company_currency)