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

            # Creamos los pagos por las lineas de pago
            self._create_lines_payment_payments()
            # try:
            #     has_invoices = len(self.account_move_line_payment_agg_ids) > 0
            #     has_payment_methods = len(self.mps_payment_methods_line_ids) > 0
            #     has_payment_account = self.payment_account > 0
               
            #     _logger.info(f"=== DIAGNÓSTICO AGRUPADOR {self.name} ===")
            #     _logger.info(f"Facturas: {has_invoices} ({len(self.account_move_line_payment_agg_ids)} líneas)")
            #     _logger.info(f"Métodos de pago: {has_payment_methods} ({len(self.mps_payment_methods_line_ids)} líneas)")
            #     _logger.info(f"Pago a cuenta: {has_payment_account} (${self.payment_account})")
               
            #     if has_invoices and has_payment_methods:
            #         # CASO MIXTO: Facturas + Métodos de pago específicos
            #         _logger.info("=== EJECUTANDO CASO MIXTO ===")
            #         self._create_mixed_payments()
                   
            #     elif has_invoices and not has_payment_methods:
            #         # CASO 1: Solo facturas (sin métodos específicos)
            #         _logger.info("=== EJECUTANDO SOLO FACTURAS ===")
            #         self._create_invoices_payment()
            #         if has_payment_account:
            #             self._create_payment_account_if_needed_with_invoices()
                       
            #     else:
            #         # CASO 2: Solo pago a cuenta (sin facturas)
            #         _logger.info("=== EJECUTANDO SOLO PAGO A CUENTA ===")
            #         self._create_lines_payment_payments_v2()

            #     # VERIFICAR ESTADO FINAL DE TODOS LOS PAGOS
            #     final_payments = self.env['account.payment'].search([
            #         ('payment_aggregator_id', '=', self.id)
            #     ])
               
            #     draft_payments = final_payments.filtered(lambda p: p.state == 'draft')
            #     posted_payments = final_payments.filtered(lambda p: p.state == 'posted')
               
            #     _logger.info(f"=== RESULTADO FINAL ===")
            #     _logger.info(f"Pagos creados: {len(final_payments)}")
            #     _logger.info(f"Pagos confirmados: {len(posted_payments)}")
            #     _logger.info(f"Pagos en borrador: {len(draft_payments)}")
               
            #     if draft_payments:
            #         _logger.warning("ADVERTENCIA: Algunos pagos quedaron en borrador:")
            #         for payment in draft_payments:
            #             _logger.warning(f"- {payment.name}: {payment.state} - Monto: {payment.amount}")
               
            #     # Intentar confirmar pagos que quedaron en borrador
            #     for payment in draft_payments:
            #         try:
            #             _logger.info(f"Intentando confirmar pago pendiente: {payment.name}")
            #             payment.action_post()
            #             if payment.state == 'posted':
            #                 _logger.info(f"✓ Pago confirmado exitosamente: {payment.name}")
            #             else:
            #                 _logger.warning(f"✗ Pago sigue en borrador: {payment.name}")
            #         except Exception as e:
            #             _logger.error(f"✗ Error confirmando {payment.name}: {str(e)}")

            # except Exception as e:
            #     _logger.error(f"Error en button_change_state: {str(e)}")
            #     raise UserError(str(e))
               
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
                    'currency_id': self.currency_id.id,  # MONEDA DEL MÉTODO
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
            payment_details['amount'] = payment_method["amount"] if self.currency_id.id != self.env.company.currency_id.id else payment_method["payment_amount"]
            payment_details['amount_destino'] = payment_method["amount"]
            payment_details['payment_type'] = payment_method["payment_type"]
            payment_details['payment_type_mps'] = payment_method["payment_type"]
            # payment_details['is_internal_transfer'] = True   # Marcamos
            # payment_details['is_internal_transfer_mps'] = True   # Marcamos
            payment_details['ref'] = _('Internal Transfer')   # Referencia
            payment_details['payment_method_line_id'] = payment_method["payment_method_line_id"]["id"]
            payment_details['payment_method_id'] = payment_method["payment_method_line_id"]["payment_method_id"]["id"]
            # payment_details['transaction_type'] = "internal_transfer"
            payment_details['currency_id'] = self.currency_id.id if self.currency_id.id != self.env.company.currency_id.id else payment_method["currency_id"].id
           
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

            # CORREGIDO: Comparar moneda del agrupador vs moneda de la línea del método de pago
            if payment_method.currency_id.id != self.currency_id.id:
                # Calcular la tasa de cambio correcta
                currency_rate = 1.0
                if payment_method["payment_currency_amount"] and payment_method["amount"]:
                    if payment_method["currency_id"].id == self.env.company.currency_id.id:
                        currency_rate = payment_method["payment_currency_amount"] / payment_method["amount"]
                    else:
                        currency_rate = payment_method["amount"] / payment_method["payment_currency_amount"]
                
                # CORREGIDO: Guardar el currency_rate correcto en una variable
                # para restaurarlo después de action_post
                correct_currency_rate = currency_rate
                
                # Actualizar las líneas del asiento con los montos correctos
                self._update_move_lines_with_correct_amounts(
                    payment, 
                    payment_method, 
                    currency_rate
                )
                
                # LOG: Verificar estado antes de actualizar
                _logger.info("=== ANTES DE ACTUALIZAR CURRENCY_RATE ===")
                _logger.info("Payment ID: %s", payment.id)
                _logger.info("Payment currency_rate ANTES: %s", payment.currency_rate)
                _logger.info("Move ID: %s", payment.move_id.id if payment.move_id else "None")
                _logger.info("Move currency_rate: %s", payment.move_id.currency_rate if payment.move_id else "None")
                _logger.info("Currency_rate calculado: %s", currency_rate)

                # CORREGIDO: Actualizar currency_rate del pago directamente
                # Ya que el método _compute_currency_rate no se ejecuta automáticamente
                try:
                    payment.write({
                        'currency_rate': currency_rate,
                    })
                    _logger.info("Payment.write() ejecutado exitosamente")
                except Exception as e:
                    _logger.error("Error en payment.write(): %s", str(e))

                # LOG: Verificar estado después de actualizar
                _logger.info("=== DESPUÉS DE ACTUALIZAR CURRENCY_RATE ===")
                _logger.info("Payment currency_rate DESPUÉS: %s", payment.currency_rate)
                _logger.info("Move currency_rate DESPUÉS: %s", payment.move_id.currency_rate if payment.move_id else "None")

                # CORREGIDO: Llamar action_post y restaurar el valor correcto después
                payment.action_post()
                
                # Restaurar el currency_rate correcto después de action_post
                _logger.info("Restaurando currency_rate correcto: %s", correct_currency_rate)
                payment.write({
                    'currency_rate': correct_currency_rate
                })
                
                # También actualizar el asiento contable
                if payment.move_id:
                    payment.move_id.write({
                        'currency_rate': correct_currency_rate
                    })
                for line in payment.move_id.line_ids:
                    if line.account_id.account_type in ('asset_receivable', 'liability_payable'):
                        line.write({'account_id': self.get_account()})
            else:
                payment.action_post()
    # Modificación de asientos con fechas correctas
        amount = payment_method["amount"]

        # account_account = self.env["account.journal"].search([
        #     ('type', '=', 'sale' if self.receiptbook_id.partner_type == "customer" else 'purchase')
        # ], limit=1)
        # payment.write({
        #     "partner_type": self.receiptbook_id.partner_type,
        #     "account_journal_id": account_account.id,
        #     "currency_id": self.currency_id.id,
        #     "amount_total_signed": payment_method["payment_amount"],
        #     "amount_company_currency_signed": payment_method["payment_amount"],
        #     # REMOVER: "currency_rate": payment_method["payment_currency_amount"]/payment_method["amount"],
        # })
        # payment.action_draft()
        # payment.action_post()

        _logger.info(payment)
        _logger.info(payment.partner_type)
        _logger.info(self.receiptbook_id.partner_type)

    def _update_move_lines_with_correct_amounts(self, payment, payment_method, currency_rate):
        """
        Actualizar las líneas del asiento contable con los montos correctos
        basados en la tasa de cambio personalizada
        CORREGIDO: Usar la moneda del agrupador en lugar de la moneda del método de pago
        """
        company_currency = self.env.company.currency_id
        # CORREGIDO: Usar la moneda del agrupador (que es la moneda del pago)
        aggregator_currency = self.currency_id

        # Si la moneda del agrupador es igual a la de la compañía, no hay conversión necesaria
        if aggregator_currency.id == company_currency.id and payment_method.currency_id.id == company_currency.id:
            return

        line_ids = []
        for line in payment.move_id.line_ids:
            vals = {}
            if line.account_id.account_type in (
            'asset_receivable', 'liability_payable') and aggregator_currency == company_currency:
                vals.update({'account_id': self.get_account()})
            if line.debit > 0:
                # Línea débito
                # CORREGIDO: amount_currency debe ser el monto en la moneda del agrupador
                amount_currency = float(
                    payment_method["amount"]) if payment_method.currency_id.id == company_currency.id else float(
                    payment_method["payment_amount"])  # Monto en moneda del agrupador
                amount_company = amount_currency * currency_rate

                vals.update({
                    'debit': amount_company,
                    'balance': amount_company,
                    'amount_currency': amount_currency,
                    'currency_id': payment_method.currency_id.id if aggregator_currency == company_currency else aggregator_currency,
                    # CORREGIDO: Moneda del agrupador
                })

            elif line.credit > 0:
                # Línea crédito
                # CORREGIDO: amount_currency debe ser el monto en la moneda del agrupador
                amount_currency = float(
                    payment_method["amount"]) if payment_method.currency_id.id == company_currency.id else float(
                    payment_method["payment_amount"])  # Monto en moneda del agrupador
                amount_company = amount_currency * currency_rate

                vals.update({
                    'credit': amount_company,
                    'balance': -amount_company,
                    'amount_currency': -amount_currency,
                    'currency_id': payment_method.currency_id.id if aggregator_currency == company_currency else aggregator_currency,
                    # CORREGIDO: Moneda del agrupador
                })

            if vals:
                line_ids.append((1, line.id, vals))

        if line_ids:
            payment.move_id.write({'line_ids': line_ids, 'currency_rate': currency_rate})

        _logger.info(f"Updated payment {payment.name} with custom currency_rate: {currency_rate}")
        _logger.info(
            f"Payment currency: {aggregator_currency.name}, Amount in currency: {amount_currency}, Amount in company: {amount_company}")

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
        """
        Filtra las líneas contables cuando cambia el cliente o la moneda.
        
        Este método busca las líneas contables pendientes de pago para el cliente
        y moneda seleccionados, y crea registros temporales para mostrar en la vista.
        """
        # Buscar líneas contables pendientes
        credit_lines = self.search_account_move_line()
        _logger.info(f"Líneas contables encontradas: {len(credit_lines)} para cliente {self.customer_id} y moneda {self.currency_id}")
        
        # Asignar las líneas encontradas
        self.mps_credits_line_ids = credit_lines
        
        # Limpiar registros de agregador existentes
        self.account_move_line_payment_agg_ids = [(5, 0, 0)]
        
        # Crear registros temporales para mostrar en la vista (solo si hay líneas)
        if credit_lines and self.id:  # Solo si el registro ya tiene ID (no es nuevo)
            self.set_account_move_line(credit_lines)
        elif credit_lines and not self.id:  # Si es un registro nuevo, crear registros temporales
            # Crear registros temporales que se guardarán cuando se guarde el registro principal
            temp_aggregator_ids = []
            for credit_line in credit_lines:
                if credit_line.amount_residual != 0 and credit_line.parent_state != 'cancel':
                    # Crear registro temporal sin guardar en la base de datos
                    temp_record = self.env['account.move.line.payment.aggregator'].new({
                        'account_move_line_id': credit_line.id,
                        'payment_aggregator_id': False,  # Se asignará cuando se guarde
                        'payment_aggregator_amount_currency': credit_line.amount_currency,
                        'payment_aggregator_amount_residual': credit_line.amount_residual_currency
                    })
                    temp_data = {
                        'account_move_line_id': credit_line.id,
                        'payment_aggregator_amount_currency': credit_line.amount_currency,
                        'payment_aggregator_amount_residual': credit_line.amount_residual_currency
                    }
                    _logger.info(f"Creando datos temporales para línea {credit_line.id}: {temp_data}")
                    temp_aggregator_ids.append((0, 0, temp_data))
            _logger.info(f"Total de registros temporales creados: {len(temp_aggregator_ids)}")
            self.account_move_line_payment_agg_ids = temp_aggregator_ids

        # Buscar diario intermedio para la moneda seleccionada
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
        """
        Crea registros de agregador de pago para las líneas contables seleccionadas.
        
        Este método crea registros de referencia que apuntan a las líneas contables originales
        sin crear nuevas líneas contables, evitando así problemas con fechas de bloqueo de impuestos.
        
        Args:
            credit_lines: Lista de líneas contables a procesar
        """
        aggregator_ids = []
        if credit_lines:
            for credit_line in credit_lines:
                # Validar que la línea contable sea válida y tenga ID
                if not credit_line or not credit_line.id:
                    _logger.warning(f"Línea contable inválida o sin ID: {credit_line}")
                    continue
                    
                if credit_line.amount_residual != 0 and credit_line.parent_state != 'cancel':
                    try:
                        # Crear el registro de referencia sin crear nuevas líneas contables
                        aggregator_record = self.env['account.move.line.payment.aggregator'].create({
                            'account_move_line_id': credit_line.id,
                            'payment_aggregator_id': self.id,
                            'payment_aggregator_amount_currency': credit_line.amount_currency,
                            'payment_aggregator_amount_residual': credit_line.amount_residual_currency
                        })
                        aggregator_ids.append(aggregator_record.id)
                        _logger.info(f"Registro creado exitosamente para línea contable ID: {credit_line.id}")
                    except Exception as e:
                        _logger.error(f"Error creando registro para línea contable ID {credit_line.id}: {e}")
                        continue
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
        """
        Crea un nuevo agrupador de pagos y crea los registros de agregador correspondientes.
        """
        values['company_id'] = self.env.company.id
        
        # Extraer los registros temporales de agregador si existen
        temp_aggregator_data = []
        if 'account_move_line_payment_agg_ids' in values:
            temp_aggregator_data = values.pop('account_move_line_payment_agg_ids')
        
        result = super().create(values)
        result.name = self.env['ir.sequence'].next_by_code('aggregator.sequence')
        
        # Debug: Verificar qué datos tenemos disponibles
        _logger.info(f"=== DEBUG CREATE ===")
        _logger.info(f"result.mps_credits_line_ids: {result.mps_credits_line_ids}")
        _logger.info(f"len(result.mps_credits_line_ids): {len(result.mps_credits_line_ids)}")
        _logger.info(f"temp_aggregator_data: {temp_aggregator_data}")
        _logger.info(f"len(temp_aggregator_data): {len(temp_aggregator_data) if temp_aggregator_data else 0}")
        
        # Crear registros de agregador después de que el registro principal tenga ID
        # Usar mps_credits_line_ids directamente en lugar de datos temporales
        if result.mps_credits_line_ids:
            _logger.info(f"Creando registros de agregador para {len(result.mps_credits_line_ids)} líneas contables")
            result.set_account_move_line(result.mps_credits_line_ids)
        elif temp_aggregator_data:
            _logger.info(f"Procesando {len(temp_aggregator_data)} registros temporales de agregador")
            # Procesar los datos temporales que incluyen las modificaciones del usuario
            account_move_line_ids = []
            for i, command in enumerate(temp_aggregator_data):
                _logger.info(f"Procesando comando {i}: {command}")
                if command[0] == 0:  # create command
                    command_data = command[2]
                    # Si el usuario editó el importe, usar ese valor
                    if 'payment_aggregator_total_import' in command_data:
                        # Buscar la línea contable correspondiente usando el índice
                        if result.customer_id and result.currency_id:
                            credit_lines = result.search_account_move_line()
                            if i < len(credit_lines):
                                credit_line = credit_lines[i]
                                # Crear registro con el importe editado por el usuario
                                aggregator_data = {
                                    'account_move_line_id': credit_line.id,
                                    'payment_aggregator_id': result.id,
                                    'payment_aggregator_amount_currency': credit_line.amount_currency,
                                    'payment_aggregator_amount_residual': command_data['payment_aggregator_total_import']
                                }
                                _logger.info(f"Creando registro con importe editado: {aggregator_data}")
                                self.env['account.move.line.payment.aggregator'].create(aggregator_data)
                                account_move_line_ids.append(credit_line.id)
                    elif 'account_move_line_id' in command_data and command_data['account_move_line_id']:
                        # Si tiene account_move_line_id, usar directamente
                        command_data['payment_aggregator_id'] = result.id
                        _logger.info(f"Creando registro con datos completos: {command_data}")
                        self.env['account.move.line.payment.aggregator'].create(command_data)
                        account_move_line_ids.append(command_data['account_move_line_id'])
            
            # Asignar las líneas contables al registro principal
            if account_move_line_ids:
                _logger.info(f"Asignando {len(account_move_line_ids)} líneas contables al registro principal")
                result.with_context(skip_aggregator_sync=True).mps_credits_line_ids = [(6, 0, account_move_line_ids)]
        
        return result
    
    def write(self, values):
        """
        Actualiza el agrupador de pagos y sincroniza los registros de agregador.
        """
        res = super().write(values)
        
        # Solo procesar si realmente hay cambios en las líneas contables
        # y no estamos en el proceso de creación inicial
        if 'mps_credits_line_ids' in values and not self._context.get('skip_aggregator_sync'):
            _logger.info(f"Actualizando registros de agregador para {len(self.mps_credits_line_ids)} líneas contables")
            
            # Verificar si realmente hay cambios en las líneas contables
            current_line_ids = set(self.account_move_line_payment_agg_ids.mapped('account_move_line_id.id'))
            new_line_ids = set(self.mps_credits_line_ids.ids)
            
            if current_line_ids != new_line_ids:
                _logger.info(f"Detectados cambios en líneas contables. Actuales: {len(current_line_ids)}, Nuevas: {len(new_line_ids)}")
                # Solo limpiar y recrear si realmente hay cambios
                if self.mps_credits_line_ids:
                    # Limpiar registros existentes solo si hay nuevas líneas
                    self.account_move_line_payment_agg_ids = [(5, 0, 0)]
                    # Crear nuevos registros
                    self.set_account_move_line(self.mps_credits_line_ids)
                else:
                    # Si no hay líneas contables, limpiar registros de agregador
                    _logger.info("No hay líneas contables, limpiando registros de agregador")
                    self.account_move_line_payment_agg_ids = [(5, 0, 0)]
            else:
                _logger.info("No hay cambios en las líneas contables, omitiendo actualización")
        
        return res
   
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
       
        # if payment_currency.id == company_currency.id:
        #     amount_company_currency = amount_in_payment_currency
        # else:
            # amount_company_currency = payment_currency._convert(
            #     amount_in_payment_currency,
            #     company_currency,
            #     self.env.company,
            #     date
            # )
        amount_company_currency = payment_method["payment_amount"]
       
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
       
        _logger.info(payment.currency_id.name)
        _logger.info("Updated payment %s with amounts: payment_currency=%.2f, company_currency=%.2f",
                     payment.name, amount_in_payment_currency, amount_company_currency)

    def button_reconciliate_payments(self):
        payments = self.env["account.payment"].search([("payment_aggregator_id","=",self.id)])
        for credit_line in self.account_move_line_payment_agg_ids:
            for payment in payments:
                account_partial_reconcile = self.env['account.partial.reconcile']
                # Reconciliar pago con factura
                payment_lines = payment.line_ids.filtered(
                    lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
                )
                invoice_lines = credit_line.move_id.line_ids.filtered(
                    lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
                )

                partial_reconcile = account_partial_reconcile.search([("debit_move_id","=",invoice_lines.id),("credit_move_id","=",payment_lines.id)],limit=1) 

                if not partial_reconcile:
                    account_partial_reconcile.create({
                        'debit_move_id': invoice_lines.id,
                        'credit_move_id': payment_lines.id,
                        'amount': credit_line.payment_aggregator_total_import,   # en moneda de la compañía (UYU)
                        'debit_amount_currency': credit_line.payment_aggregator_total_import,  # moneda de la factura
                        'credit_amount_currency': credit_line.payment_aggregator_total_import,   # moneda del pago
                        'max_date': self.date
                    })

    def button_reconciliate_payments_improved(self):
        """
        MÉTODO MEJORADO: Reconcilia pagos con facturas según payment_aggregator_total_import
        
        Este método implementa correctamente la lógica de reconciliación:
        1. Obtiene todos los pagos del agrupador
        2. Para cada factura con monto asignado (payment_aggregator_total_import > 0)
        3. Distribuye los pagos proporcionalmente según los montos asignados
        4. Reconcilia usando el API estándar de Odoo
        """
        try:
            _logger.info(f"=== INICIANDO RECONCILIACIÓN MEJORADA PARA AGRUPADOR {self.name} ===")
            
            # Validar que el agrupador esté en estado publicado
            if self.state != 'published':
                raise UserError(_("El agrupador debe estar publicado para reconciliar pagos"))
            
            # Determinar qué lógica usar según el tipo del talonario
            if self.receiptbook_id.partner_type == 'supplier':
                _logger.info("Usando lógica específica para PROVEEDORES")
                return self._reconciliate_payments_suppliers()
            else:
                _logger.info("Usando lógica específica para CLIENTES")
                return self._reconciliate_payments_customers()

        except Exception as e:
            _logger.error(f"Error en reconciliación mejorada: {str(e)}")
            raise UserError(f"Error durante la reconciliación: {str(e)}")

    def _reconciliate_payments_suppliers(self):
        """
        Lógica específica para reconciliación de proveedores
        """
        _logger.info(f"=== RECONCILIACIÓN ESPECÍFICA PARA PROVEEDORES - AGRUPADOR {self.name} ===")

        # Obtener facturas con monto asignado
        invoices_to_reconcile = self.account_move_line_payment_agg_ids.filtered(
            lambda line: line.payment_aggregator_total_import > 0
        )

        if not invoices_to_reconcile:
            raise UserError(_("No hay facturas con montos asignados para reconciliar"))

        _logger.info(f"Facturas a reconciliar: {len(invoices_to_reconcile)}")

        # Para proveedores, crear pagos individuales usando el diario del talonario
        created_payments = []

        for invoice_line in invoices_to_reconcile:
            invoice = invoice_line.move_id
            amount = invoice_line.payment_aggregator_total_import
            currency = invoice.currency_id

            _logger.info(f"Creando pago para factura de proveedor {invoice.name} - Monto: {amount} - Moneda: {currency.name}")

            # Usar el diario intermedio para la moneda del agrupador (no el diario del talonario)
            payment_journal = self._get_intermediate_journal_for_currency(currency)
            
            if not payment_journal:
                _logger.warning(f"No se encontró diario intermedio para moneda {currency.name}, usando diario del agrupador")
                payment_journal = self.receiptbook_id.account_journal_id

            # Determinar tipo de pago basado en el talonario
            if self.receiptbook_id.type == 'outbound':
                payment_type = 'outbound'  # Pagamos al proveedor
                partner_type = 'supplier'
            else:
                payment_type = 'inbound'  # Recibimos del proveedor
                partner_type = 'supplier'

            # Buscar método de pago apropiado en el diario intermedio
            if payment_type == 'inbound':
                method_line = payment_journal.inbound_payment_method_line_ids.filtered(
                    lambda m: m.payment_method_id.code == 'manual'
                )[:1] or payment_journal.inbound_payment_method_line_ids[:1]
            else:
                method_line = payment_journal.outbound_payment_method_line_ids.filtered(
                    lambda m: m.payment_method_id.code == 'manual'
                )[:1] or payment_journal.outbound_payment_method_line_ids[:1]

            _logger.info(f"Usando diario intermedio: {payment_journal.name}")
            _logger.info(f"Método de pago encontrado: {method_line.payment_method_id.name if method_line else 'Ninguno'}")

            # Crear pago
            payment_vals = {
                'payment_type': payment_type,
                'partner_type': partner_type,
                'partner_id': invoice.partner_id.id,
                'amount': amount,
                'currency_id': currency.id,
                'journal_id': payment_journal.id,
                'date': self.date,
                'ref': f'Pago automático proveedor - {invoice.name}',
                'payment_method_line_id': method_line.id if method_line else False,
                'payment_aggregator_id': self.id,
            }

            try:
                payment = self.env['account.payment'].create(payment_vals)
                payment.action_post()

                # Modificar el asiento para usar las cuentas correctas del campo "pago a cuenta"
                self._modify_payment_account_for_supplier(payment, currency, payment_journal)

                # Reconciliar con la factura
                self._reconcile_supplier_payment_with_invoice(payment, invoice)

                created_payments.append(payment)
                _logger.info(f"✓ Pago creado y reconciliado: {payment.name}")

            except Exception as e:
                _logger.error(f"Error creando pago para factura {invoice.name}: {e}")

        # Crear pago contrario que reconcilie contra los métodos de pago del agrupador
        if created_payments:
            _logger.info(f"Creando pago contrario para reconciliar con métodos de pago del agrupador")
            # Convertir lista a recordset para poder usar .mapped()
            payments_recordset = self.env['account.payment'].browse([p.id for p in created_payments])
            reverse_payment = self._create_reverse_payment_for_suppliers(payments_recordset)

            if reverse_payment:
                _logger.info(f"Reconciliando pago contrario con métodos de pago del agrupador")
                # Buscar pagos existentes del agrupador (métodos de pago)
                existing_payments = self.env['account.payment'].search([
                    ('payment_aggregator_id', '=', self.id),
                    ('state', '=', 'posted'),
                    ('id', '!=', reverse_payment.id),  # Excluir el pago contrario
                    ('ref', 'not ilike', 'Pago automático proveedor'),  # Excluir pagos de facturas
                    ('ref', 'not ilike', 'Pago inverso proveedor'),  # Excluir otros pagos inversos
                ])
                self._reconcile_reverse_payment_with_methods(reverse_payment, existing_payments)

        _logger.info(f"=== RECONCILIACIÓN PROVEEDORES COMPLETADA - {len(created_payments)} pagos creados ===")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reconciliación Proveedores Completada'),
                'message': _(f'Se crearon y reconciliaron {len(created_payments)} pagos para proveedores.'),
                'type': 'success',
                'sticky': True,
            }
        }

    def _reconciliate_payments_customers(self):
        """
        Lógica original para reconciliación de clientes (que funcionaba antes)
        """
        _logger.info(f"=== RECONCILIACIÓN ESPECÍFICA PARA CLIENTES - AGRUPADOR {self.name} ===")

        # Obtener todos los pagos confirmados del agrupador
        payments = self.env["account.payment"].search([
            ("payment_aggregator_id", "=", self.id),
            ("state", "=", "posted")
        ])

        if not payments:
            raise UserError(_("No se encontraron pagos confirmados para reconciliar"))

        # Obtener facturas con monto asignado
        invoices_to_reconcile = self.account_move_line_payment_agg_ids.filtered(
            lambda line: line.payment_aggregator_total_import > 0
        )

        if not invoices_to_reconcile:
            raise UserError(_("No hay facturas con montos asignados para reconciliar"))

        _logger.info(f"Pagos encontrados: {len(payments)}")
        _logger.info(f"Facturas a reconciliar: {len(invoices_to_reconcile)}")

        # Calcular el monto total asignado a facturas
        total_assigned_amount = sum(invoices_to_reconcile.mapped('payment_aggregator_total_import'))
        total_payments_amount = sum(payments.mapped('amount'))

        _logger.info(f"Monto total asignado a facturas: {total_assigned_amount}")
        _logger.info(f"Monto total de pagos: {total_payments_amount}")

        # Validar que los montos coincidan (con tolerancia de centavos)
        if abs(total_assigned_amount - total_payments_amount) > 0.01:
            _logger.warning(f"Diferencia en montos: Asignado={total_assigned_amount}, Pagos={total_payments_amount}")

        # Para clientes, primero corregir las cuentas de los pagos existentes
        _logger.info("Corrigiendo cuentas de pagos existentes para clientes")
        for payment in payments:
            try:
                # Obtener la moneda del pago
                currency = payment.currency_id

                # Usar el diario del talonario para obtener las cuentas correctas
                payment_journal = self.receiptbook_id.account_journal_id

                # Modificar las cuentas del pago para que sean correctas para clientes
                self._modify_payment_account_for_customer(payment, currency, payment_journal)

            except Exception as e:
                _logger.error(f"Error corrigiendo cuentas del pago {payment.name}: {e}")

        # Procesar cada factura individualmente usando la lógica original
        reconciliation_results = []

        for invoice_line in invoices_to_reconcile:
            result = self._reconcile_invoice_with_payments(
                invoice_line,
                payments,
                total_assigned_amount
            )
            reconciliation_results.append(result)

        # Resumen de resultados
        successful_reconciliations = [r for r in reconciliation_results if r['success']]
        failed_reconciliations = [r for r in reconciliation_results if not r['success']]

        _logger.info(f"=== RESUMEN DE RECONCILIACIÓN ===")
        _logger.info(f"Reconciliaciones exitosas: {len(successful_reconciliations)}")
        _logger.info(f"Reconciliaciones fallidas: {len(failed_reconciliations)}")

        if failed_reconciliations:
            failed_invoices = [r['invoice_name'] for r in failed_reconciliations]
            _logger.warning(f"Facturas con errores: {failed_invoices}")

        # Actualizar estados de facturas
        self._update_invoice_payment_states()

        _logger.info(f"=== RECONCILIACIÓN CLIENTES COMPLETADA PARA AGRUPADOR {self.name} ===")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reconciliación Completada'),
                'message': _(f'Se procesaron {len(successful_reconciliations)} facturas exitosamente. '
                           f'{len(failed_reconciliations)} facturas con errores.'),
                'type': 'success' if not failed_reconciliations else 'warning',
                'sticky': True,
            }
        }

    def _reconcile_invoice_with_payments(self, invoice_line, payments, total_assigned_amount):
        """
        Reconcilia una factura específica con los pagos disponibles
        
        Args:
            invoice_line: Línea de factura del agrupador (account.move.line.payment.aggregator)
            payments: Recordset de pagos disponibles
            total_assigned_amount: Monto total asignado a todas las facturas
            
        Returns:
            dict: Resultado de la reconciliación
        """
        try:
            invoice_move = invoice_line.move_id
            assigned_amount = invoice_line.payment_aggregator_total_import
            
            _logger.info(f"Procesando factura {invoice_move.name} con monto asignado: {assigned_amount}")
            
            # Obtener líneas de factura pendientes de reconciliación
            invoice_move_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not invoice_move_lines:
                return {
                    'success': False,
                    'invoice_name': invoice_move.name,
                    'error': 'No se encontraron líneas de factura pendientes de reconciliación'
                }
            
            # Distribuir pagos proporcionalmente para esta factura
            remaining_to_reconcile = assigned_amount
            reconciled_amount = 0
            
            for payment in payments:
                if remaining_to_reconcile <= 0.01:  # Ya se reconcilió todo
                    break
                
                # Calcular la proporción de este pago que corresponde a esta factura
                if total_assigned_amount > 0:
                    payment_proportion = assigned_amount / total_assigned_amount
                else:
                    payment_proportion = 1.0 / len(payments)  # Distribuir equitativamente
                
                # Monto de este pago que se debe asignar a esta factura
                payment_amount_for_invoice = payment.amount * payment_proportion
                
                # No exceder el monto restante por reconciliar
                amount_to_reconcile = min(payment_amount_for_invoice, remaining_to_reconcile)
                
                if amount_to_reconcile > 0.01:  # Solo procesar si hay monto significativo
                    success = self._reconcile_specific_invoice_amount(
                        payment, 
                        invoice_move, 
                        amount_to_reconcile
                    )
                    
                    if success:
                        reconciled_amount += amount_to_reconcile
                        remaining_to_reconcile -= amount_to_reconcile
                        _logger.info(f"Reconciliado {amount_to_reconcile} del pago {payment.name} con factura {invoice_move.name}")
                    else:
                        _logger.warning(f"Falló reconciliación de {amount_to_reconcile} del pago {payment.name} con factura {invoice_move.name}")
            
            # Verificar si se reconcilió completamente
            if remaining_to_reconcile > 0.01:
                _logger.warning(f"Factura {invoice_move.name}: Falta reconciliar {remaining_to_reconcile}")
            
            return {
                'success': True,
                'invoice_name': invoice_move.name,
                'assigned_amount': assigned_amount,
                'reconciled_amount': reconciled_amount,
                'remaining_amount': remaining_to_reconcile
            }
            
        except Exception as e:
            _logger.error(f"Error reconciliando factura {invoice_line.move_id.name}: {str(e)}")
            return {
                'success': False,
                'invoice_name': invoice_line.move_id.name,
                'error': str(e)
            }

    def _update_invoice_payment_states(self):
        """
        Actualiza los estados de pago de todas las facturas del agrupador
        """
        try:
            for invoice_line in self.account_move_line_payment_agg_ids:
                invoice_move = invoice_line.move_id
                if invoice_move:
                    # Recalcular el estado de pago de la factura
                    invoice_move._compute_payment_state()
                    _logger.info(f"Estado de pago actualizado para factura {invoice_move.name}: {invoice_move.payment_state}")
                    
        except Exception as e:
            _logger.error(f"Error actualizando estados de facturas: {str(e)}")

    def _get_payment_distribution_for_invoice(self, invoice_line, payments, total_assigned_amount):
        """
        Calcula cómo distribuir los pagos para una factura específica
        
        Returns:
            list: Lista de tuplas (payment, amount_to_assign)
        """
        assigned_amount = invoice_line.payment_aggregator_total_import
        distribution = []
        
        for payment in payments:
            # Calcular proporción de este pago para esta factura
            if total_assigned_amount > 0:
                proportion = assigned_amount / total_assigned_amount
            else:
                proportion = 1.0 / len(self.account_move_line_payment_agg_ids.filtered(
                    lambda l: l.payment_aggregator_total_import > 0
                ))
            
            amount_to_assign = payment.amount * proportion
            
            if amount_to_assign > 0.01:  # Solo incluir montos significativos
                distribution.append((payment, amount_to_assign))
        
        return distribution

    def button_validate_reconciliation_setup(self):
        """
        Método auxiliar para validar que la configuración de reconciliación esté correcta
        antes de ejecutar la reconciliación
        """
        try:
            _logger.info(f"Validando configuración de reconciliación para agrupador {self.name}")
            
            # Validar estado del agrupador
            if self.state != 'published':
                raise ValidationError(_("El agrupador debe estar publicado"))
            
            # Validar pagos
            payments = self.env["account.payment"].search([
                ("payment_aggregator_id", "=", self.id),
                ("state", "=", "posted")
            ])
            
            if not payments:
                raise ValidationError(_("No hay pagos confirmados asociados al agrupador"))
            
            # Validar facturas con asignación
            invoices_with_assignment = self.account_move_line_payment_agg_ids.filtered(
                lambda line: line.payment_aggregator_total_import > 0
            )
            
            if not invoices_with_assignment:
                raise ValidationError(_("No hay facturas con montos asignados"))
            
            # Validar montos
            total_assigned = sum(invoices_with_assignment.mapped('payment_aggregator_total_import'))
            total_payments = sum(payments.mapped('amount'))
            
            if abs(total_assigned - total_payments) > 0.01:
                raise ValidationError(_(
                    f"Los montos no coinciden:\n"
                    f"Total asignado a facturas: {total_assigned}\n"
                    f"Total de pagos: {total_payments}\n"
                    f"Diferencia: {abs(total_assigned - total_payments)}"
                ))
            
            # Validar que las facturas no estén ya completamente reconciliadas
            already_paid_invoices = []
            for invoice_line in invoices_with_assignment:
                invoice_move = invoice_line.move_id
                if invoice_move.payment_state == 'paid':
                    already_paid_invoices.append(invoice_move.name)
            
            if already_paid_invoices:
                _logger.warning(f"Facturas ya pagadas: {already_paid_invoices}")
            
            validation_result = {
                'payments_count': len(payments),
                'invoices_count': len(invoices_with_assignment),
                'total_assigned': total_assigned,
                'total_payments': total_payments,
                'already_paid_invoices': already_paid_invoices
            }
            
            _logger.info(f"Validación exitosa: {validation_result}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Validación Exitosa'),
                    'message': _(
                        f'Configuración válida:\n'
                        f'• {len(payments)} pagos confirmados\n'
                        f'• {len(invoices_with_assignment)} facturas con asignación\n'
                        f'• Montos coinciden: ${total_assigned}\n'
                        f'{"• Algunas facturas ya están pagadas" if already_paid_invoices else ""}'
                    ),
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except ValidationError as ve:
            raise ve
        except Exception as e:
            _logger.error(f"Error en validación: {str(e)}")
            raise UserError(f"Error durante la validación: {str(e)}")

    def get_account(self):
        for rec in self:
            if rec.receiptbook_id and rec.receiptbook_id.account_journal_id:
                for line_conf in rec.sudo().receiptbook_id.account_journal_id.account_currency_ids:
                    if line_conf.currency_id.id == self.currency_id.id:
                        return line_conf.account_id.id
            return None

    def button_reconciliate_payments_advanced(self):
        """
        MÉTODO AVANZADO: Reconcilia pagos con facturas manejando diferentes monedas y cuentas
        
        Este método resuelve los problemas de:
        1. Diferentes monedas entre pagos y facturas
        2. Diferentes cuentas contables (pesos vs USD)
        3. Reconciliaciones parciales complejas
        """
        try:
            _logger.info(f"=== INICIANDO RECONCILIACIÓN AVANZADA PARA AGRUPADOR {self.name} ===")
            
            # Validar que el agrupador esté en estado publicado
            if self.state != 'published':
                raise UserError(_("El agrupador debe estar publicado para reconciliar pagos"))
            
            # Obtener todos los pagos confirmados del agrupador
            payments = self.env["account.payment"].search([
                ("payment_aggregator_id", "=", self.id),
                ("state", "=", "posted")
            ])
            
            if not payments:
                raise UserError(_("No se encontraron pagos confirmados para reconciliar"))
            
            # Obtener facturas con monto asignado
            invoices_to_reconcile = self.account_move_line_payment_agg_ids.filtered(
                lambda line: line.payment_aggregator_total_import > 0
            )
            
            if not invoices_to_reconcile:
                raise UserError(_("No hay facturas con montos asignados para reconciliar"))
            
            _logger.info(f"Pagos encontrados: {len(payments)}")
            _logger.info(f"Facturas a reconciliar: {len(invoices_to_reconcile)}")
            
            # Calcular el monto total asignado a facturas
            total_assigned_amount = sum(invoices_to_reconcile.mapped('payment_aggregator_total_import'))
            total_payments_amount = sum(payments.mapped('amount'))
            
            _logger.info(f"Monto total asignado a facturas: {total_assigned_amount}")
            _logger.info(f"Monto total de pagos: {total_payments_amount}")
            
            # Procesar cada factura individualmente con reconciliación avanzada
            reconciliation_results = []
            
            for invoice_line in invoices_to_reconcile:
                result = self._reconcile_invoice_advanced(
                    invoice_line, 
                    payments, 
                    total_assigned_amount
                )
                reconciliation_results.append(result)
            
            # Resumen de resultados
            successful_reconciliations = [r for r in reconciliation_results if r['success']]
            failed_reconciliations = [r for r in reconciliation_results if not r['success']]
            
            _logger.info(f"=== RESUMEN DE RECONCILIACIÓN AVANZADA ===")
            _logger.info(f"Reconciliaciones exitosas: {len(successful_reconciliations)}")
            _logger.info(f"Reconciliaciones fallidas: {len(failed_reconciliations)}")
            
            if failed_reconciliations:
                failed_invoices = [r['invoice_name'] for r in failed_reconciliations]
                _logger.warning(f"Facturas con errores: {failed_invoices}")
            
            # Actualizar estados de facturas
            self._update_invoice_payment_states()
            
            _logger.info(f"=== RECONCILIACIÓN AVANZADA COMPLETADA PARA AGRUPADOR {self.name} ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reconciliación Avanzada Completada'),
                    'message': _(f'Se procesaron {len(successful_reconciliations)} facturas exitosamente. '
                               f'{len(failed_reconciliations)} facturas con errores.'),
                    'type': 'success' if not failed_reconciliations else 'warning',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en reconciliación avanzada: {str(e)}")
            raise UserError(f"Error durante la reconciliación avanzada: {str(e)}")

    def _reconcile_invoice_advanced(self, invoice_line, payments, total_assigned_amount):
        """
        Reconcilia una factura específica con los pagos usando reconciliación avanzada
        
        Args:
            invoice_line: Línea de factura del agrupador (account.move.line.payment.aggregator)
            payments: Recordset de pagos disponibles
            total_assigned_amount: Monto total asignado a todas las facturas
            
        Returns:
            dict: Resultado de la reconciliación
        """
        try:
            invoice_move = invoice_line.move_id
            assigned_amount = invoice_line.payment_aggregator_total_import
            
            _logger.info(f"Procesando factura {invoice_move.name} con monto asignado: {assigned_amount}")
            _logger.info(f"Moneda de la factura: {invoice_move.currency_id.name}")
            
            # Obtener líneas de factura pendientes de reconciliación
            invoice_move_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not invoice_move_lines:
                return {
                    'success': False,
                    'invoice_name': invoice_move.name,
                    'error': 'No se encontraron líneas de factura pendientes de reconciliación'
                }
            
            _logger.info(f"Líneas de factura encontradas: {len(invoice_move_lines)}")
            for line in invoice_move_lines:
                _logger.info(f"  - Cuenta: {line.account_id.code} {line.account_id.name}, Moneda: {line.currency_id.name if line.currency_id else 'Sin moneda'}")
            
            # Distribuir pagos proporcionalmente para esta factura
            remaining_to_reconcile = assigned_amount
            reconciled_amount = 0
            
            for payment in payments:
                if remaining_to_reconcile <= 0.01:  # Ya se reconcilió todo
                    break
                
                _logger.info(f"Procesando pago {payment.name} - Moneda: {payment.currency_id.name}")
                
                # Calcular la proporción de este pago que corresponde a esta factura
                if total_assigned_amount > 0:
                    payment_proportion = assigned_amount / total_assigned_amount
                else:
                    payment_proportion = 1.0 / len(payments)  # Distribuir equitativamente
                
                # Monto de este pago que se debe asignar a esta factura
                payment_amount_for_invoice = payment.amount * payment_proportion
                
                # No exceder el monto restante por reconciliar
                amount_to_reconcile = min(payment_amount_for_invoice, remaining_to_reconcile)
                
                if amount_to_reconcile > 0.01:  # Solo procesar si hay monto significativo
                    success = self._reconcile_with_currency_handling(
                        payment, 
                        invoice_move, 
                        amount_to_reconcile
                    )
                    
                    if success:
                        reconciled_amount += amount_to_reconcile
                        remaining_to_reconcile -= amount_to_reconcile
                        _logger.info(f"✓ Reconciliado {amount_to_reconcile} del pago {payment.name} con factura {invoice_move.name}")
                    else:
                        _logger.warning(f"✗ Falló reconciliación de {amount_to_reconcile} del pago {payment.name} con factura {invoice_move.name}")
            
            # Verificar si se reconcilió completamente
            if remaining_to_reconcile > 0.01:
                _logger.warning(f"Factura {invoice_move.name}: Falta reconciliar {remaining_to_reconcile}")
            
            return {
                'success': True,
                'invoice_name': invoice_move.name,
                'assigned_amount': assigned_amount,
                'reconciled_amount': reconciled_amount,
                'remaining_amount': remaining_to_reconcile
            }
            
        except Exception as e:
            _logger.error(f"Error reconciliando factura {invoice_line.move_id.name}: {str(e)}")
            return {
                'success': False,
                'invoice_name': invoice_line.move_id.name,
                'error': str(e)
            }

    def _reconcile_with_currency_handling(self, payment, invoice_move, amount_to_reconcile):
        """
        Reconcilia un pago con una factura manejando diferentes monedas y cuentas
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
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
            
            _logger.info(f"Intentando reconciliar pago {payment.name} con factura {invoice_move.name}")
            _logger.info(f"Líneas de pago: {len(payment_lines)}")
            _logger.info(f"Líneas de factura: {len(invoice_lines)}")
            
            # ESTRATEGIA 1: Intentar reconciliación directa con todas las líneas
            try:
                _logger.info("Estrategia 1: Reconciliación directa con todas las líneas")
                (payment_lines + invoice_lines).reconcile()
                _logger.info("✓ Reconciliación directa exitosa")
                return True
            except Exception as e1:
                _logger.warning(f"Estrategia 1 falló: {str(e1)}")
            
            # ESTRATEGIA 2: Reconciliación línea por línea
            try:
                _logger.info("Estrategia 2: Reconciliación línea por línea")
                for payment_line in payment_lines:
                    for invoice_line in invoice_lines:
                        try:
                            # Verificar que las cuentas sean compatibles
                            if self._are_accounts_compatible(payment_line.account_id, invoice_line.account_id):
                                _logger.info(f"Reconciliando línea de pago {payment_line.id} con línea de factura {invoice_line.id}")
                                (payment_line + invoice_line).reconcile()
                                _logger.info("✓ Reconciliación línea por línea exitosa")
                                return True
                        except Exception as e2:
                            _logger.warning(f"Error reconciliando líneas específicas: {str(e2)}")
                            continue
            except Exception as e2:
                _logger.warning(f"Estrategia 2 falló: {str(e2)}")
            
            # ESTRATEGIA 3: Crear reconciliación parcial manual
            try:
                _logger.info("Estrategia 3: Reconciliación parcial manual")
                return self._create_manual_partial_reconcile(payment_lines, invoice_lines, amount_to_reconcile)
            except Exception as e3:
                _logger.warning(f"Estrategia 3 falló: {str(e3)}")
            
            # ESTRATEGIA 4: Reconciliación por monto residual
            try:
                _logger.info("Estrategia 4: Reconciliación por monto residual")
                return self._reconcile_by_residual_amount(payment_lines, invoice_lines, amount_to_reconcile)
            except Exception as e4:
                _logger.warning(f"Estrategia 4 falló: {str(e4)}")
            
            _logger.error(f"Todas las estrategias de reconciliación fallaron para pago {payment.name} con factura {invoice_move.name}")
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación con manejo de monedas: {str(e)}")
            return False

    def _are_accounts_compatible(self, account1, account2):
        """
        Verifica si dos cuentas son compatibles para reconciliación
        
        Args:
            account1: Primera cuenta
            account2: Segunda cuenta
            
        Returns:
            bool: True si las cuentas son compatibles
        """
        try:
            # Verificar que ambas cuentas sean del mismo tipo
            if account1.account_type != account2.account_type:
                return False
            
            # Verificar que ambas cuentas sean de cuentas por cobrar/pagar
            if account1.account_type not in ['asset_receivable', 'liability_payable']:
                return False
            
            # Verificar que ambas cuentas pertenezcan al mismo partner (si aplica)
            # Esto es opcional, pero puede ayudar en algunos casos
            
            return True
            
        except Exception as e:
            _logger.warning(f"Error verificando compatibilidad de cuentas: {str(e)}")
            return False

    def _create_manual_partial_reconcile(self, payment_lines, invoice_lines, amount_to_reconcile):
        """
        Crea una reconciliación parcial manual usando el modelo account.partial.reconcile
        
        Args:
            payment_lines: Líneas de pago
            invoice_lines: Líneas de factura
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            # Usar la primera línea de cada tipo
            payment_line = payment_lines[0]
            invoice_line = invoice_lines[0]
            
            # Determinar cuál es débito y cuál es crédito
            if payment_line.debit > 0:
                debit_line = payment_line
                credit_line = invoice_line
            else:
                debit_line = invoice_line
                credit_line = payment_line
            
            # Crear la reconciliación parcial sin el campo amount_currency que causa error
            partial_rec_vals = {
                'amount': amount_to_reconcile,
                'debit_move_id': debit_line.id,
                'credit_move_id': credit_line.id,
            }
            
            # Solo agregar currency_id si ambas líneas tienen la misma moneda
            if (payment_line.currency_id and invoice_line.currency_id and 
                payment_line.currency_id.id == invoice_line.currency_id.id):
                partial_rec_vals['currency_id'] = payment_line.currency_id.id
            
            partial_rec = self.env['account.partial.reconcile'].create(partial_rec_vals)
            
            _logger.info(f"✓ Reconciliación parcial manual creada: {partial_rec.id}")
            return True
            
        except Exception as e:
            _logger.error(f"Error creando reconciliación parcial manual: {str(e)}")
            return False

    def _reconcile_by_residual_amount(self, payment_lines, invoice_lines, amount_to_reconcile):
        """
        Reconcilia basándose en el monto residual disponible
        
        Args:
            payment_lines: Líneas de pago
            invoice_lines: Líneas de factura
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            for payment_line in payment_lines:
                for invoice_line in invoice_lines:
                    # Calcular el monto máximo que se puede reconciliar
                    max_payment_amount = abs(payment_line.amount_residual)
                    max_invoice_amount = abs(invoice_line.amount_residual)
                    max_reconcile = min(max_payment_amount, max_invoice_amount, amount_to_reconcile)
                    
                    if max_reconcile > 0.01:  # Solo procesar si hay monto significativo
                        try:
                            # Intentar reconciliación directa
                            (payment_line + invoice_line).reconcile()
                            _logger.info(f"✓ Reconciliación por monto residual exitosa: {max_reconcile}")
                            return True
                        except Exception as e:
                            _logger.warning(f"Error en reconciliación por monto residual: {str(e)}")
                            continue
            
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación por monto residual: {str(e)}")
            return False

    def button_reconciliate_payments_final(self):
        """
        MÉTODO FINAL: Reconcilia pagos con facturas corrigiendo problemas de cuentas
        
        Este método resuelve el problema específico de:
        1. Facturas en USD usando cuenta de pesos (110400)
        2. Pagos en USD usando cuenta de USD (110401)
        3. Necesidad de reconciliar entre cuentas diferentes
        """
        try:
            _logger.info(f"=== INICIANDO RECONCILIACIÓN FINAL PARA AGRUPADOR {self.name} ===")
            
            # Validar que el agrupador esté en estado publicado
            if self.state != 'published':
                raise UserError(_("El agrupador debe estar publicado para reconciliar pagos"))
            
            # Obtener todos los pagos confirmados del agrupador
            payments = self.env["account.payment"].search([
                ("payment_aggregator_id", "=", self.id),
                ("state", "=", "posted")
            ])
            
            if not payments:
                raise UserError(_("No se encontraron pagos confirmados para reconciliar"))
            
            # Obtener facturas con monto asignado
            invoices_to_reconcile = self.account_move_line_payment_agg_ids.filtered(
                lambda line: line.payment_aggregator_total_import > 0
            )
            
            if not invoices_to_reconcile:
                raise UserError(_("No hay facturas con montos asignados para reconciliar"))
            
            _logger.info(f"Pagos encontrados: {len(payments)}")
            _logger.info(f"Facturas a reconciliar: {len(invoices_to_reconcile)}")
            
            # Procesar cada factura individualmente con reconciliación final
            reconciliation_results = []
            
            for invoice_line in invoices_to_reconcile:
                result = self._reconcile_invoice_final(
                    invoice_line, 
                    payments
                )
                reconciliation_results.append(result)
            
            # Resumen de resultados
            successful_reconciliations = [r for r in reconciliation_results if r['success']]
            failed_reconciliations = [r for r in reconciliation_results if not r['success']]
            
            _logger.info(f"=== RESUMEN DE RECONCILIACIÓN FINAL ===")
            _logger.info(f"Reconciliaciones exitosas: {len(successful_reconciliations)}")
            _logger.info(f"Reconciliaciones fallidas: {len(failed_reconciliations)}")
            
            if failed_reconciliations:
                failed_invoices = [r['invoice_name'] for r in failed_reconciliations]
                _logger.warning(f"Facturas con errores: {failed_invoices}")
            
            # Actualizar estados de facturas
            self._update_invoice_payment_states()
            
            _logger.info(f"=== RECONCILIACIÓN FINAL COMPLETADA PARA AGRUPADOR {self.name} ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reconciliación Final Completada'),
                    'message': _(f'Se procesaron {len(successful_reconciliations)} facturas exitosamente. '
                               f'{len(failed_reconciliations)} facturas con errores.'),
                    'type': 'success' if not failed_reconciliations else 'warning',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en reconciliación final: {str(e)}")
            raise UserError(f"Error durante la reconciliación final: {str(e)}")

    def _reconcile_invoice_final(self, invoice_line, payments):
        """
        Reconcilia una factura específica con los pagos usando reconciliación final
        
        Args:
            invoice_line: Línea de factura del agrupador (account.move.line.payment.aggregator)
            payments: Recordset de pagos disponibles
            
        Returns:
            dict: Resultado de la reconciliación
        """
        try:
            invoice_move = invoice_line.move_id
            assigned_amount = invoice_line.payment_aggregator_total_import
            
            _logger.info(f"Procesando factura {invoice_move.name} con monto asignado: {assigned_amount}")
            _logger.info(f"Moneda de la factura: {invoice_move.currency_id.name}")
            
            # Obtener líneas de factura pendientes de reconciliación
            invoice_move_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not invoice_move_lines:
                return {
                    'success': False,
                    'invoice_name': invoice_move.name,
                    'error': 'No se encontraron líneas de factura pendientes de reconciliación'
                }
            
            _logger.info(f"Líneas de factura encontradas: {len(invoice_move_lines)}")
            for line in invoice_move_lines:
                _logger.info(f"  - Cuenta: {line.account_id.code} {line.account_id.name}, Moneda: {line.currency_id.name if line.currency_id else 'Sin moneda'}")
            
            # Buscar pagos que coincidan con la moneda de la factura
            matching_payments = payments.filtered(
                lambda p: p.currency_id.id == invoice_move.currency_id.id
            )
            
            if not matching_payments:
                _logger.warning(f"No se encontraron pagos en la moneda {invoice_move.currency_id.name} para la factura {invoice_move.name}")
                return {
                    'success': False,
                    'invoice_name': invoice_move.name,
                    'error': f'No hay pagos en la moneda {invoice_move.currency_id.name}'
                }
            
            _logger.info(f"Pagos coincidentes encontrados: {len(matching_payments)}")
            
            # Intentar reconciliación directa con pagos de la misma moneda
            reconciled_amount = 0
            remaining_to_reconcile = assigned_amount
            
            for payment in matching_payments:
                if remaining_to_reconcile <= 0.01:
                    break
                
                _logger.info(f"Procesando pago {payment.name} - Moneda: {payment.currency_id.name}")
                
                # Calcular el monto a reconciliar de este pago
                payment_amount_for_invoice = min(payment.amount, remaining_to_reconcile)
                
                if payment_amount_for_invoice > 0.01:
                    success = self._reconcile_with_account_correction(
                        payment, 
                        invoice_move, 
                        payment_amount_for_invoice
                    )
                    
                    if success:
                        reconciled_amount += payment_amount_for_invoice
                        remaining_to_reconcile -= payment_amount_for_invoice
                        _logger.info(f"✓ Reconciliado {payment_amount_for_invoice} del pago {payment.name} con factura {invoice_move.name}")
                    else:
                        _logger.warning(f"✗ Falló reconciliación de {payment_amount_for_invoice} del pago {payment.name} con factura {invoice_move.name}")
            
            # Verificar si se reconcilió completamente
            if remaining_to_reconcile > 0.01:
                _logger.warning(f"Factura {invoice_move.name}: Falta reconciliar {remaining_to_reconcile}")
            
            return {
                'success': True,
                'invoice_name': invoice_move.name,
                'assigned_amount': assigned_amount,
                'reconciled_amount': reconciled_amount,
                'remaining_amount': remaining_to_reconcile
            }
            
        except Exception as e:
            _logger.error(f"Error reconciliando factura {invoice_line.move_id.name}: {str(e)}")
            return {
                'success': False,
                'invoice_name': invoice_line.move_id.name,
                'error': str(e)
            }

    def _reconcile_with_account_correction(self, payment, invoice_move, amount_to_reconcile):
        """
        Reconcilia un pago con una factura corrigiendo problemas de cuentas
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
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
            
            _logger.info(f"Intentando reconciliar pago {payment.name} con factura {invoice_move.name}")
            _logger.info(f"Líneas de pago: {len(payment_lines)}")
            _logger.info(f"Líneas de factura: {len(invoice_lines)}")
            
            # ESTRATEGIA 1: Intentar reconciliación directa
            try:
                _logger.info("Estrategia 1: Reconciliación directa")
                (payment_lines + invoice_lines).reconcile()
                _logger.info("✓ Reconciliación directa exitosa")
                return True
            except Exception as e1:
                _logger.warning(f"Estrategia 1 falló: {str(e1)}")
            
            # ESTRATEGIA 2: Corregir cuentas y reconciliar
            try:
                _logger.info("Estrategia 2: Corrección de cuentas y reconciliación")
                return self._reconcile_with_account_fix(payment_lines, invoice_lines, amount_to_reconcile)
            except Exception as e2:
                _logger.warning(f"Estrategia 2 falló: {str(e2)}")
            
            # ESTRATEGIA 3: Crear asiento de ajuste
            try:
                _logger.info("Estrategia 3: Crear asiento de ajuste")
                return self._create_adjustment_entry(payment, invoice_move, amount_to_reconcile)
            except Exception as e3:
                _logger.warning(f"Estrategia 3 falló: {str(e3)}")
            
            _logger.error(f"Todas las estrategias de reconciliación fallaron para pago {payment.name} con factura {invoice_move.name}")
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación con corrección de cuentas: {str(e)}")
            return False

    def _reconcile_with_account_fix(self, payment_lines, invoice_lines, amount_to_reconcile):
        """
        Reconcilia corrigiendo temporalmente las cuentas
        
        Args:
            payment_lines: Líneas de pago
            invoice_lines: Líneas de factura
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            # Obtener las cuentas correctas
            payment_account = payment_lines[0].account_id
            invoice_account = invoice_lines[0].account_id
            
            _logger.info(f"Cuenta de pago: {payment_account.code} - {payment_account.name}")
            _logger.info(f"Cuenta de factura: {invoice_account.code} - {invoice_account.name}")
            
            # Si las cuentas son diferentes, intentar encontrar una cuenta común
            if payment_account.id != invoice_account.id:
                # Buscar una cuenta que sea compatible con ambas
                common_account = self._find_common_account(payment_account, invoice_account)
                
                if common_account:
                    _logger.info(f"Usando cuenta común: {common_account.code} - {common_account.name}")
                    
                    # Temporalmente cambiar las cuentas a la cuenta común
                    payment_lines.write({'account_id': common_account.id})
                    invoice_lines.write({'account_id': common_account.id})
                    
                    try:
                        # Intentar reconciliación
                        (payment_lines + invoice_lines).reconcile()
                        _logger.info("✓ Reconciliación con cuenta común exitosa")
                        return True
                    except Exception as e:
                        _logger.warning(f"Error en reconciliación con cuenta común: {str(e)}")
                    finally:
                        # Restaurar las cuentas originales
                        payment_lines.write({'account_id': payment_account.id})
                        invoice_lines.write({'account_id': invoice_account.id})
            
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación con corrección de cuentas: {str(e)}")
            return False

    def _find_common_account(self, account1, account2):
        """
        Busca una cuenta común que sea compatible con ambas cuentas
        
        Args:
            account1: Primera cuenta
            account2: Segunda cuenta
            
        Returns:
            account: Cuenta común encontrada o None
        """
        try:
            # Buscar cuentas del mismo tipo y partner
            common_accounts = self.env['account.account'].search([
                ('account_type', '=', account1.account_type),
                ('company_id', '=', self.env.company.id),
                ('reconcile', '=', True)
            ])
            
            # Si hay cuentas comunes, usar la primera
            if common_accounts:
                return common_accounts[0]
            
            return None
            
        except Exception as e:
            _logger.warning(f"Error buscando cuenta común: {str(e)}")
            return None

    def _create_adjustment_entry(self, payment, invoice_move, amount_to_reconcile):
        """
        Crea un asiento de ajuste para reconciliar entre cuentas diferentes
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            _logger.info(f"Creando asiento de ajuste para reconciliar {amount_to_reconcile}")
            
            # Obtener las cuentas
            payment_account = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
            )[0].account_id
            
            invoice_account = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
            )[0].account_id
            
            # Crear asiento de ajuste
            adjustment_move = self.env['account.move'].create({
                'move_type': 'entry',
                'date': self.date,
                'ref': f'Ajuste de reconciliación - {self.name}',
                'line_ids': [
                    (0, 0, {
                        'account_id': payment_account.id,
                        'debit': amount_to_reconcile,
                        'credit': 0,
                        'partner_id': self.customer_id.id,
                        'currency_id': payment.currency_id.id,
                    }),
                    (0, 0, {
                        'account_id': invoice_account.id,
                        'debit': 0,
                        'credit': amount_to_reconcile,
                        'partner_id': self.customer_id.id,
                        'currency_id': invoice_move.currency_id.id,
                    }),
                ]
            })
            
            # Confirmar el asiento
            adjustment_move.action_post()
            
            _logger.info(f"✓ Asiento de ajuste creado: {adjustment_move.name}")
            
            # Ahora reconciliar las líneas originales con el asiento de ajuste
            payment_lines = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
            )
            
            invoice_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
            )
            
            adjustment_lines = adjustment_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
            )
            
            # Reconciliar pago con asiento de ajuste
            if payment_lines and adjustment_lines:
                (payment_lines + adjustment_lines).reconcile()
                _logger.info("✓ Pago reconciliado con asiento de ajuste")
            
            # Reconciliar factura con asiento de ajuste
            if invoice_lines and adjustment_lines:
                (invoice_lines + adjustment_lines).reconcile()
                _logger.info("✓ Factura reconciliada con asiento de ajuste")
            
            return True
            
        except Exception as e:
            _logger.error(f"Error creando asiento de ajuste: {str(e)}")
            return False

    def button_reconciliate_payments_sequential(self):
        """
        MÉTODO SECUENCIAL: Reconcilia pagos con facturas de forma secuencial
        
        Comportamiento correcto:
        1. Toma el primer pago y lo reconcilia con facturas hasta agotar su monto
        2. Luego toma el segundo pago y lo reconcilia con las facturas restantes
        3. Continúa hasta procesar todos los pagos
        """
        try:
            _logger.info(f"=== INICIANDO RECONCILIACIÓN SECUENCIAL PARA AGRUPADOR {self.name} ===")
            
            # Validar que el agrupador esté en estado publicado
            if self.state != 'published':
                raise UserError(_("El agrupador debe estar publicado para reconciliar pagos"))
            
            # Obtener todos los pagos confirmados del agrupador
            payments = self.env["account.payment"].search([
                ("payment_aggregator_id", "=", self.id),
                ("state", "=", "posted")
            ])
            
            if not payments:
                raise UserError(_("No se encontraron pagos confirmados para reconciliar"))
            
            # Obtener facturas con monto asignado
            invoices_to_reconcile = self.account_move_line_payment_agg_ids.filtered(
                lambda line: line.payment_aggregator_total_import > 0
            )
            
            if not invoices_to_reconcile:
                raise UserError(_("No hay facturas con montos asignados para reconciliar"))
            
            _logger.info(f"Pagos encontrados: {len(payments)}")
            _logger.info(f"Facturas a reconciliar: {len(invoices_to_reconcile)}")
            
            # Calcular el monto total asignado a facturas
            total_assigned_amount = sum(invoices_to_reconcile.mapped('payment_aggregator_total_import'))
            total_payments_amount = sum(payments.mapped('amount'))
            
            _logger.info(f"Monto total asignado a facturas: {total_assigned_amount}")
            _logger.info(f"Monto total de pagos: {total_payments_amount}")
            
            # Procesar cada pago secuencialmente
            reconciliation_results = []
            
            for payment in payments:
                _logger.info(f"=== PROCESANDO PAGO {payment.name} - Monto: {payment.amount} - Moneda: {payment.currency_id.name} ===")
                
                # CORREGIDO: Obtener facturas restantes antes de cada pago
                remaining_invoices = self.account_move_line_payment_agg_ids.filtered(
                    lambda line: line.payment_aggregator_total_import > 0
                )
                
                _logger.info(f"Facturas restantes antes del pago {payment.name}: {len(remaining_invoices)}")
                
                # Distribuir este pago secuencialmente entre las facturas restantes
                result = self._distribute_payment_sequentially(
                    payment, 
                    remaining_invoices
                )
                reconciliation_results.append(result)
                
                _logger.info(f"Facturas restantes después del pago {payment.name}: {len(self.account_move_line_payment_agg_ids.filtered(lambda line: line.payment_aggregator_total_import > 0))}")
            
            # Resumen de resultados
            successful_reconciliations = [r for r in reconciliation_results if r['success']]
            failed_reconciliations = [r for r in reconciliation_results if not r['success']]
            
            _logger.info(f"=== RESUMEN DE RECONCILIACIÓN SECUENCIAL ===")
            _logger.info(f"Pagos procesados exitosamente: {len(successful_reconciliations)}")
            _logger.info(f"Pagos con errores: {len(failed_reconciliations)}")
            
            if failed_reconciliations:
                failed_payments = [r['payment_name'] for r in failed_reconciliations]
                _logger.warning(f"Pagos con errores: {failed_payments}")
            
            # Actualizar estados de facturas
            self._update_invoice_payment_states()
            
            _logger.info(f"=== RECONCILIACIÓN SECUENCIAL COMPLETADA PARA AGRUPADOR {self.name} ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reconciliación Secuencial Completada'),
                    'message': _(f'Se procesaron {len(successful_reconciliations)} pagos exitosamente. '
                               f'{len(failed_reconciliations)} pagos con errores.'),
                    'type': 'success' if not failed_reconciliations else 'warning',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en reconciliación secuencial: {str(e)}")
            raise UserError(f"Error durante la reconciliación secuencial: {str(e)}")

    def _distribute_payment_sequentially(self, payment, remaining_invoices):
        """
        Distribuye un pago secuencialmente entre las facturas restantes
        
        Args:
            payment: Pago a distribuir
            remaining_invoices: Facturas restantes por reconciliar
            
        Returns:
            dict: Resultado de la distribución
        """
        try:
            _logger.info(f"Distribuyendo pago {payment.name} secuencialmente")
            
            # Obtener líneas de pago pendientes de reconciliación
            payment_lines = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not payment_lines:
                _logger.warning(f"No se encontraron líneas de pago pendientes para {payment.name}")
                return {
                    'success': False,
                    'payment_name': payment.name,
                    'error': 'No hay líneas de pago pendientes de reconciliación'
                }
            
            _logger.info(f"Líneas de pago pendientes: {len(payment_lines)}")
            
            # Distribuir el pago secuencialmente entre las facturas restantes
            reconciled_amount = 0
            remaining_payment_amount = payment.amount
            invoices_processed = []
            
            # CORREGIDO: Iterar sobre cada factura individualmente
            for invoice_line in remaining_invoices:
                if remaining_payment_amount <= 0.01:
                    _logger.info(f"Pago {payment.name} agotado, no se puede reconciliar más facturas")
                    break
                
                # CORREGIDO: Acceder al campo del registro individual
                assigned_amount = invoice_line.payment_aggregator_total_import
                if assigned_amount <= 0:
                    _logger.info(f"Factura {invoice_line.move_id.name} ya está completamente reconciliada, saltando")
                    continue
                
                # Monto a reconciliar: el menor entre el monto restante del pago y el monto asignado a la factura
                amount_to_reconcile = min(remaining_payment_amount, assigned_amount)
                
                if amount_to_reconcile > 0.01:
                    _logger.info(f"Reconciliando {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                    
                    success = self._reconcile_payment_with_invoice_sequential(
                        payment, 
                        invoice_line.move_id, 
                        amount_to_reconcile
                    )
                    
                    if success:
                        reconciled_amount += amount_to_reconcile
                        remaining_payment_amount -= amount_to_reconcile
                        
                        # CORREGIDO: Actualizar el monto asignado a la factura usando write()
                        invoice_line.write({
                            'payment_aggregator_total_import': assigned_amount - amount_to_reconcile
                        })
                        
                        invoices_processed.append({
                            'invoice_name': invoice_line.move_id.name,
                            'amount_reconciled': amount_to_reconcile,
                            'remaining_assigned': assigned_amount - amount_to_reconcile
                        })
                        
                        _logger.info(f"✓ Reconciliado {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                        _logger.info(f"  - Monto restante del pago: {remaining_payment_amount}")
                        _logger.info(f"  - Monto restante asignado a la factura: {assigned_amount - amount_to_reconcile}")
                    else:
                        _logger.warning(f"✗ Falló reconciliación de {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
            
            # Verificar si se reconcilió completamente
            if remaining_payment_amount > 0.01:
                _logger.warning(f"Pago {payment.name}: Falta reconciliar {remaining_payment_amount}")
            
            return {
                'success': True,
                'payment_name': payment.name,
                'total_amount': payment.amount,
                'reconciled_amount': reconciled_amount,
                'remaining_amount': remaining_payment_amount,
                'invoices_processed': invoices_processed
            }
            
        except Exception as e:
            _logger.error(f"Error distribuyendo pago {payment.name} secuencialmente: {str(e)}")
            return {
                'success': False,
                'payment_name': payment.name,
                'error': str(e)
            }

    def _reconcile_payment_with_invoice_sequential(self, payment, invoice_move, amount_to_reconcile):
        """
        Reconcilia un pago específico con una factura específica de forma secuencial
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            # CORREGIDO: Buscar líneas de pago que tengan saldo residual (no solo no reconciliadas)
            payment_lines = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and abs(line.amount_residual) > 0.01  # Cambiado: buscar por saldo residual
            )
            
            # Obtener líneas de factura pendientes de reconciliación
            invoice_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not payment_lines or not invoice_lines:
                _logger.warning(f"No se encontraron líneas para reconciliar: pago {payment.name} con factura {invoice_move.name}")
                _logger.warning(f"Líneas de pago con saldo residual: {len(payment_lines)}")
                _logger.warning(f"Líneas de factura pendientes: {len(invoice_lines)}")
                return False
            
            _logger.info(f"Reconciliando pago {payment.name} con factura {invoice_move.name}")
            _logger.info(f"Líneas de pago con saldo residual: {len(payment_lines)}")
            _logger.info(f"Líneas de factura: {len(invoice_lines)}")
            
            # ESTRATEGIA 1: Intentar reconciliación directa
            try:
                _logger.info("Estrategia 1: Reconciliación directa")
                (payment_lines + invoice_lines).reconcile()
                _logger.info("✓ Reconciliación directa exitosa")
                return True
            except Exception as e1:
                _logger.warning(f"Estrategia 1 falló: {str(e1)}")
            
            # ESTRATEGIA 2: Reconciliación con corrección de cuentas
            try:
                _logger.info("Estrategia 2: Reconciliación con corrección de cuentas")
                return self._reconcile_with_account_correction_sequential(payment_lines, invoice_lines, amount_to_reconcile)
            except Exception as e2:
                _logger.warning(f"Estrategia 2 falló: {str(e2)}")
            
            # ESTRATEGIA 3: Crear asiento de ajuste
            try:
                _logger.info("Estrategia 3: Crear asiento de ajuste")
                return self._create_adjustment_entry_sequential(payment, invoice_move, amount_to_reconcile)
            except Exception as e3:
                _logger.warning(f"Estrategia 3 falló: {str(e3)}")
            
            _logger.error(f"Todas las estrategias de reconciliación fallaron para pago {payment.name} con factura {invoice_move.name}")
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación secuencial de pago con factura: {str(e)}")
            return False

    def _reconcile_with_account_correction_sequential(self, payment_lines, invoice_lines, amount_to_reconcile):
        """
        Reconcilia con corrección de cuentas de forma secuencial
        
        Args:
            payment_lines: Líneas de pago
            invoice_lines: Líneas de factura
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            # Obtener las cuentas
            payment_account = payment_lines[0].account_id
            invoice_account = invoice_lines[0].account_id
            
            _logger.info(f"Cuenta de pago: {payment_account.code} - {payment_account.name}")
            _logger.info(f"Cuenta de factura: {invoice_account.code} - {invoice_account.name}")
            
            # Si las cuentas son diferentes, crear un asiento de ajuste
            if payment_account.id != invoice_account.id:
                _logger.info("Cuentas diferentes, creando asiento de ajuste")
                return self._create_adjustment_entry_sequential(
                    payment_lines[0].move_id.payment_id, 
                    invoice_lines[0].move_id, 
                    amount_to_reconcile
                )
            
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación con corrección de cuentas secuencial: {str(e)}")
            return False

    def _create_adjustment_entry_sequential(self, payment, invoice_move, amount_to_reconcile):
        """
        Crea un asiento de ajuste para reconciliar entre cuentas diferentes con manejo correcto de monedas
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            dict: Resultado de la creación del asiento
        """
        try:
            _logger.info(f"Creando asiento de ajuste secuencial para reconciliar {amount_to_reconcile}")
            
            # CORREGIDO: Usar account_type en lugar de internal_type para Odoo 17
            payment_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and abs(l.amount_residual) > 0
            )
            invoice_lines = invoice_move.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and abs(l.amount_residual) > 0
            )
            
            if not payment_lines or not invoice_lines:
                return {'success': False, 'message': 'No se encontraron líneas válidas'}
            
            payment_line = payment_lines[0]
            invoice_line = invoice_lines[0]
            
            # CORREGIDO: Usar la moneda del pago como moneda principal
            currency_id = payment.currency_id.id
            company_currency_id = payment.company_id.currency_id.id
            
            # CORREGIDO: Calcular el monto en la moneda de la empresa
            if currency_id != company_currency_id:
                # Si el pago está en USD y la empresa en UYU, convertir
                amount_company_currency = payment.currency_id._convert(
                    amount_to_reconcile, 
                    payment.company_id.currency_id, 
                    payment.company_id, 
                    payment.date
                )
            else:
                amount_company_currency = amount_to_reconcile
            
            # Crear asiento de ajuste
            adjustment_vals = {
                'ref': f'Ajuste para reconciliación {payment.name} - {invoice_move.name}',
                'date': payment.date,
                'journal_id': payment.journal_id.id,
                'company_id': payment.company_id.id,
                'currency_id': currency_id,  # CORREGIDO: Usar moneda del pago
                'line_ids': [
                    # Línea de débito - Cuenta de la factura (pesos)
                    (0, 0, {
                        'account_id': invoice_line.account_id.id,
                        'partner_id': invoice_line.partner_id.id,
                        'name': f'Ajuste para {invoice_move.name}',
                        'debit': amount_company_currency,
                        'credit': 0.0,
                        'amount_currency': amount_to_reconcile,  # CORREGIDO: Monto en USD
                        'currency_id': currency_id,  # CORREGIDO: Moneda USD
                        'date_maturity': invoice_line.date_maturity,
                    }),
                    # Línea de crédito - Cuenta del pago (USD)
                    (0, 0, {
                        'account_id': payment_line.account_id.id,
                        'partner_id': payment_line.partner_id.id,
                        'name': f'Ajuste para {payment.name}',
                        'debit': 0.0,
                        'credit': amount_company_currency,
                        'amount_currency': -amount_to_reconcile,  # CORREGIDO: Monto en USD
                        'currency_id': currency_id,  # CORREGIDO: Moneda USD
                        'date_maturity': payment_line.date_maturity,
                    }),
                ]
            }
            
            # Crear el asiento de ajuste
            adjustment_move = self.env['account.move'].create(adjustment_vals)
            adjustment_move.action_post()
            
            _logger.info(f"✓ Asiento de ajuste secuencial creado: {adjustment_move.name}")
            
            # CORREGIDO: Usar account_type en lugar de internal_type para Odoo 17
            adjustment_lines = adjustment_move.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
            )
            
            if len(adjustment_lines) >= 2:
                # CORREGIDO: Reconciliar directamente las líneas originales con las líneas del asiento de ajuste
                # Reconciliar pago con línea de ajuste (misma cuenta)
                payment_adjustment_line = adjustment_lines.filtered(
                    lambda l: l.account_id.id == payment_line.account_id.id
                )
                if payment_adjustment_line:
                    # CORREGIDO: Usar reconciliación directa en lugar de partial_reconcile
                    (payment_line + payment_adjustment_line).reconcile()
                    _logger.info(f"✓ Pago reconciliado con línea de ajuste")
                
                # Reconciliar factura con línea de ajuste (misma cuenta)
                invoice_adjustment_line = adjustment_lines.filtered(
                    lambda l: l.account_id.id == invoice_line.account_id.id
                )
                if invoice_adjustment_line:
                    # CORREGIDO: Usar reconciliación directa en lugar de partial_reconcile
                    (invoice_line + invoice_adjustment_line).reconcile()
                    _logger.info(f"✓ Factura reconciliada con línea de ajuste")
                
                return {
                    'success': True, 
                    'adjustment_move': adjustment_move,
                    'message': f'Asiento de ajuste creado: {adjustment_move.name}'
                }
            else:
                return {'success': False, 'message': 'No se pudieron crear las líneas de ajuste correctamente'}
                
        except Exception as e:
            _logger.error(f"Error creando asiento de ajuste secuencial: {str(e)}")
            return {'success': False, 'message': str(e)}

    def button_reconciliate_payments_proportional(self):
        # Implementa la lógica para la reconciliación proporcional aquí
        pass

    def button_reconciliate_payments_partial(self):
        """
        MÉTODO DE PAGOS PARCIALES: Implementa reconciliación parcial basada en sr_partial_invoice_payment
        
        Este método:
        1. Marca los pagos como parciales (sr_is_partial = True)
        2. Crea líneas adicionales en el asiento del pago para cada monto parcial
        3. Usa partial_matching_number para agrupar líneas relacionadas
        4. Reconcilia usando el sistema de números de coincidencia
        """
        try:
            _logger.info(f"=== INICIANDO RECONCILIACIÓN PARCIAL PARA AGRUPADOR {self.name} ===")
            
            # Validar que el agrupador esté en estado publicado
            if self.state != 'published':
                raise UserError(_("El agrupador debe estar publicado para reconciliar pagos"))
            
            # Obtener todos los pagos confirmados del agrupador
            payments = self.env["account.payment"].search([
                ("payment_aggregator_id", "=", self.id),
                ("state", "=", "posted")
            ])
            
            if not payments:
                raise UserError(_("No se encontraron pagos confirmados para reconciliar"))
            
            # Obtener facturas con monto asignado
            invoices_to_reconcile = self.account_move_line_payment_agg_ids.filtered(
                lambda line: line.payment_aggregator_total_import > 0
            )
            
            if not invoices_to_reconcile:
                raise UserError(_("No hay facturas con montos asignados para reconciliar"))
            
            _logger.info(f"Pagos encontrados: {len(payments)}")
            _logger.info(f"Facturas a reconciliar: {len(invoices_to_reconcile)}")
            
            # Procesar cada pago secuencialmente
            reconciliation_results = []
            
            for payment in payments:
                _logger.info(f"=== PROCESANDO PAGO {payment.name} - Monto: {payment.amount} - Moneda: {payment.currency_id.name} ===")
                
                # Marcar el pago como parcial
                payment.write({'sr_is_partial': True})
                
                # Obtener facturas restantes para este pago
                remaining_invoices = self.account_move_line_payment_agg_ids.filtered(
                    lambda line: line.payment_aggregator_total_import > 0
                )
                
                _logger.info(f"Facturas restantes para pago {payment.name}: {len(remaining_invoices)}")
                
                # Distribuir este pago entre las facturas restantes
                result = self._distribute_payment_partial_sr(
                    payment, 
                    remaining_invoices
                )
                reconciliation_results.append(result)
            
            # Resumen de resultados
            successful_reconciliations = [r for r in reconciliation_results if r['success']]
            failed_reconciliations = [r for r in reconciliation_results if not r['success']]
            
            _logger.info(f"=== RESUMEN DE RECONCILIACIÓN PARCIAL ===")
            _logger.info(f"Pagos procesados exitosamente: {len(successful_reconciliations)}")
            _logger.info(f"Pagos con errores: {len(failed_reconciliations)}")
            
            if failed_reconciliations:
                failed_payments = [r['payment_name'] for r in failed_reconciliations]
                _logger.warning(f"Pagos con errores: {failed_payments}")
            
            # Actualizar estados de facturas
            self._update_invoice_payment_states()
            
            _logger.info(f"=== RECONCILIACIÓN PARCIAL COMPLETADA PARA AGRUPADOR {self.name} ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reconciliación Parcial Completada'),
                    'message': _(f'Se procesaron {len(successful_reconciliations)} pagos exitosamente. '
                               f'{len(failed_reconciliations)} pagos con errores.'),
                    'type': 'success' if not failed_reconciliations else 'warning',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en reconciliación parcial: {str(e)}")
            raise UserError(f"Error durante la reconciliación parcial: {str(e)}")

    def _distribute_payment_partial_sr(self, payment, remaining_invoices):
        """
        Distribuye un pago parcialmente entre las facturas restantes usando la lógica de sr_partial_invoice_payment
        
        Args:
            payment: Pago a distribuir
            remaining_invoices: Facturas restantes por reconciliar
            
        Returns:
            dict: Resultado de la distribución
        """
        try:
            _logger.info(f"Distribuyendo pago {payment.name} parcialmente usando lógica SR")
            
            # Obtener líneas de pago originales
            original_payment_lines = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.partial_matching_number
            )
            
            if not original_payment_lines:
                _logger.warning(f"No se encontraron líneas de pago originales para {payment.name}")
                return {
                    'success': False,
                    'payment_name': payment.name,
                    'error': 'No hay líneas de pago originales'
                }
            
            original_payment_line = original_payment_lines[0]
            _logger.info(f"Línea de pago original: {original_payment_line.id} - Saldo: {original_payment_line.amount_residual}")
            
            # Distribuir el pago secuencialmente entre las facturas restantes
            reconciled_amount = 0
            remaining_payment_amount = payment.amount
            invoices_processed = []
            
            for invoice_line in remaining_invoices:
                if remaining_payment_amount <= 0.01:
                    _logger.info(f"Pago {payment.name} agotado, no se puede reconciliar más facturas")
                    break
                
                assigned_amount = invoice_line.payment_aggregator_total_import
                if assigned_amount <= 0:
                    _logger.info(f"Factura {invoice_line.move_id.name} ya está completamente reconciliada, saltando")
                    continue
                
                # Monto a reconciliar: el menor entre el monto restante del pago y el monto asignado a la factura
                amount_to_reconcile = min(remaining_payment_amount, assigned_amount)
                
                if amount_to_reconcile > 0.01:
                    _logger.info(f"Reconciliando {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                    
                    success = self._reconcile_payment_partial_sr(
                        payment, 
                        invoice_line.move_id, 
                        amount_to_reconcile,
                        original_payment_line
                    )
                    
                    if success:
                        reconciled_amount += amount_to_reconcile
                        remaining_payment_amount -= amount_to_reconcile
                        
                        # Actualizar el monto asignado a la factura
                        invoice_line.write({
                            'payment_aggregator_total_import': assigned_amount - amount_to_reconcile
                        })
                        
                        invoices_processed.append({
                            'invoice_name': invoice_line.move_id.name,
                            'amount_reconciled': amount_to_reconcile,
                            'remaining_assigned': assigned_amount - amount_to_reconcile
                        })
                        
                        _logger.info(f"✓ Reconciliado {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                        _logger.info(f"  - Monto restante del pago: {remaining_payment_amount}")
                        _logger.info(f"  - Monto restante asignado a la factura: {assigned_amount - amount_to_reconcile}")
                    else:
                        _logger.warning(f"✗ Falló reconciliación de {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
            
            # Verificar si se reconcilió completamente
            if remaining_payment_amount > 0.01:
                _logger.warning(f"Pago {payment.name}: Falta reconciliar {remaining_payment_amount}")
            
            return {
                'success': True,
                'payment_name': payment.name,
                'total_amount': payment.amount,
                'reconciled_amount': reconciled_amount,
                'remaining_amount': remaining_payment_amount,
                'invoices_processed': invoices_processed
            }
            
        except Exception as e:
            _logger.error(f"Error distribuyendo pago {payment.name} parcialmente: {str(e)}")
            return {
                'success': False,
                'payment_name': payment.name,
                'error': str(e)
            }

    def _reconcile_payment_partial_sr(self, payment, invoice_move, amount_to_reconcile, original_payment_line):
        """
        Reconcilia un pago parcialmente con una factura usando EXACTAMENTE la lógica de sr_partial_invoice_payment
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            original_payment_line: Línea de pago original
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            # Obtener líneas de factura pendientes de reconciliación
            invoice_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not invoice_lines:
                _logger.warning(f"No se encontraron líneas de factura pendientes para {invoice_move.name}")
                return False
            
            invoice_line = invoice_lines[0]
            
            # IMPLEMENTACIÓN EXACTA DE sr_partial_invoice_payment
            vals_list = []
            
            # 1. Crear nueva línea de débito en el asiento del pago (igual que SR)
            vals_list.append((0, 0, {
                "account_id": invoice_line.account_id.id,
                "partner_id": invoice_line.partner_id.id,
                "name": invoice_line.name,
                "amount_currency": -amount_to_reconcile,
                "currency_id": invoice_line.currency_id.id if invoice_line.currency_id else payment.currency_id.id,
                "debit": 0.0,
                "credit": amount_to_reconcile,
                "tax_ids": [(6, 0, invoice_line.tax_ids.ids)],
                "date_maturity": invoice_line.date_maturity,
            }))
            
            # 2. Reducir la línea original del pago (igual que SR)
            vals_list.append((1, original_payment_line.id, {
                "debit": 0.0,
                "credit": original_payment_line.credit - amount_to_reconcile,
                "amount_currency": -(original_payment_line.credit - amount_to_reconcile),
            }))
            
            # 3. Aplicar cambios al asiento del pago (igual que SR)
            payment.move_id.write({"line_ids": vals_list})
            
            # 4. Generar número de coincidencia parcial (usando nuestra secuencia)
            partial_sequence = self.env["ir.sequence"].next_by_code("partial.matching.sequence") or ""
            
            # 5. Obtener la nueva línea creada (igual que SR)
            lines = payment.move_id.line_ids.filtered(
                lambda l: l.credit == amount_to_reconcile
                and l.move_id.id == payment.move_id.id
            )
            
            # 6. Asignar partial_matching_number a la nueva línea (igual que SR)
            if lines and not lines[-1].partial_matching_number:
                lines[-1].write({"partial_matching_number": partial_sequence})
            
            # 7. Buscar línea de factura correspondiente (igual que SR)
            if lines:
                move_line = invoice_move.line_ids.filtered(
                    lambda l: l.credit != amount_to_reconcile
                    and l.account_id.id == lines[-1].account_id.id
                    and l.move_id.id == invoice_move.id
                )
                
                # 8. Asignar partial_matching_number a la línea de factura (igual que SR)
                if move_line and not move_line.partial_matching_number:
                    move_line.write({"partial_matching_number": partial_sequence})
                elif move_line and move_line.partial_matching_number:
                    move_line.write({
                        "partial_matching_number": "%s,%s" % (move_line.partial_matching_number, partial_sequence)
                    })
                
                # 9. Reconciliar las líneas con el mismo partial_matching_number (igual que SR)
                lines += move_line
                result = lines.reconcile()
                
                _logger.info(f"✓ Reconciliación parcial SR exitosa con número de coincidencia: {partial_sequence}")
                return True
            
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación parcial SR de pago con factura: {str(e)}")
            return False

    def button_reconciliate_payments_sr_style(self):
        """
        MÉTODO SR STYLE: Implementa reconciliación parcial usando EXACTAMENTE la lógica de sr_partial_invoice_payment
        
        Este método:
        1. Marca los pagos como parciales (sr_is_partial = True)
        2. Crea líneas adicionales en el asiento del pago para cada monto parcial
        3. Usa partial_matching_number para agrupar líneas relacionadas
        4. Reconcilia usando el sistema de números de coincidencia
        """
        try:
            _logger.info(f"=== INICIANDO RECONCILIACIÓN SR STYLE PARA AGRUPADOR {self.name} ===")
            
            # Validar que el agrupador esté en estado publicado
            if self.state != 'published':
                raise UserError(_("El agrupador debe estar publicado para reconciliar pagos"))
            
            # Obtener todos los pagos confirmados del agrupador
            payments = self.env["account.payment"].search([
                ("payment_aggregator_id", "=", self.id),
                ("state", "=", "posted")
            ])
            
            if not payments:
                raise UserError(_("No se encontraron pagos confirmados para reconciliar"))
            
            # Obtener facturas con monto asignado
            invoices_to_reconcile = self.account_move_line_payment_agg_ids.filtered(
                lambda line: line.payment_aggregator_total_import > 0
            )
            
            if not invoices_to_reconcile:
                raise UserError(_("No hay facturas con montos asignados para reconciliar"))
            
            _logger.info(f"Pagos encontrados: {len(payments)}")
            _logger.info(f"Facturas a reconciliar: {len(invoices_to_reconcile)}")
            
            # Procesar cada pago secuencialmente usando la lógica SR
            reconciliation_results = []
            
            for payment in payments:
                _logger.info(f"=== PROCESANDO PAGO {payment.name} - Monto: {payment.amount} - Moneda: {payment.currency_id.name} ===")
                
                # Marcar el pago como parcial (igual que SR)
                payment.write({'sr_is_partial': True})
                
                # Obtener facturas restantes para este pago
                remaining_invoices = self.account_move_line_payment_agg_ids.filtered(
                    lambda line: line.payment_aggregator_total_import > 0
                )
                
                _logger.info(f"Facturas restantes para pago {payment.name}: {len(remaining_invoices)}")
                
                # Distribuir este pago entre las facturas restantes usando lógica SR
                result = self._distribute_payment_sr_style(
                    payment, 
                    remaining_invoices
                )
                reconciliation_results.append(result)
            
            # Resumen de resultados
            successful_reconciliations = [r for r in reconciliation_results if r['success']]
            failed_reconciliations = [r for r in reconciliation_results if not r['success']]
            
            _logger.info(f"=== RESUMEN DE RECONCILIACIÓN SR STYLE ===")
            _logger.info(f"Pagos procesados exitosamente: {len(successful_reconciliations)}")
            _logger.info(f"Pagos con errores: {len(failed_reconciliations)}")
            
            if failed_reconciliations:
                failed_payments = [r['payment_name'] for r in failed_reconciliations]
                _logger.warning(f"Pagos con errores: {failed_payments}")
            
            # Actualizar estados de facturas
            self._update_invoice_payment_states()
            
            _logger.info(f"=== RECONCILIACIÓN SR STYLE COMPLETADA PARA AGRUPADOR {self.name} ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reconciliación SR Style Completada'),
                    'message': _(f'Se procesaron {len(successful_reconciliations)} pagos exitosamente. '
                               f'{len(failed_reconciliations)} pagos con errores.'),
                    'type': 'success' if not failed_reconciliations else 'warning',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en reconciliación SR style: {str(e)}")
            raise UserError(f"Error durante la reconciliación SR style: {str(e)}")

    def _distribute_payment_sr_style(self, payment, remaining_invoices):
        """
        Distribuye un pago entre las facturas restantes usando EXACTAMENTE la lógica de sr_partial_invoice_payment
        
        Args:
            payment: Pago a distribuir
            remaining_invoices: Facturas restantes por reconciliar
            
        Returns:
            dict: Resultado de la distribución
        """
        try:
            _logger.info(f"Distribuyendo pago {payment.name} usando lógica SR")
            
            # Obtener línea de pago original (igual que SR)
            original_payment_line = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.partial_matching_number
            )
            
            if not original_payment_line:
                _logger.warning(f"No se encontró línea de pago original para {payment.name}")
                return {
                    'success': False,
                    'payment_name': payment.name,
                    'error': 'No hay línea de pago original'
                }
            
            original_payment_line = original_payment_line[0]
            _logger.info(f"Línea de pago original: {original_payment_line.id} - Saldo: {original_payment_line.amount_residual}")
            
            # Distribuir el pago secuencialmente entre las facturas restantes
            reconciled_amount = 0
            remaining_payment_amount = payment.amount
            invoices_processed = []
            
            for invoice_line in remaining_invoices:
                if remaining_payment_amount <= 0.01:
                    _logger.info(f"Pago {payment.name} agotado, no se puede reconciliar más facturas")
                    break
                
                assigned_amount = invoice_line.payment_aggregator_total_import
                if assigned_amount <= 0:
                    _logger.info(f"Factura {invoice_line.move_id.name} ya está completamente reconciliada, saltando")
                    continue
                
                # Monto a reconciliar: el menor entre el monto restante del pago y el monto asignado a la factura
                amount_to_reconcile = min(remaining_payment_amount, assigned_amount)
                
                if amount_to_reconcile > 0.01:
                    _logger.info(f"Reconciliando {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                    
                    success = self._reconcile_payment_sr_style(
                        payment, 
                        invoice_line.move_id, 
                        amount_to_reconcile,
                        original_payment_line
                    )
                    
                    if success:
                        reconciled_amount += amount_to_reconcile
                        remaining_payment_amount -= amount_to_reconcile
                        
                        # Actualizar el monto asignado a la factura
                        invoice_line.write({
                            'payment_aggregator_total_import': assigned_amount - amount_to_reconcile
                        })
                        
                        invoices_processed.append({
                            'invoice_name': invoice_line.move_id.name,
                            'amount_reconciled': amount_to_reconcile,
                            'remaining_assigned': assigned_amount - amount_to_reconcile
                        })
                        
                        _logger.info(f"✓ Reconciliado {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                        _logger.info(f"  - Monto restante del pago: {remaining_payment_amount}")
                        _logger.info(f"  - Monto restante asignado a la factura: {assigned_amount - amount_to_reconcile}")
                    else:
                        _logger.warning(f"✗ Falló reconciliación de {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
            
            # Verificar si se reconcilió completamente
            if remaining_payment_amount > 0.01:
                _logger.warning(f"Pago {payment.name}: Falta reconciliar {remaining_payment_amount}")
            
            return {
                'success': True,
                'payment_name': payment.name,
                'total_amount': payment.amount,
                'reconciled_amount': reconciled_amount,
                'remaining_amount': remaining_payment_amount,
                'invoices_processed': invoices_processed
            }
            
        except Exception as e:
            _logger.error(f"Error distribuyendo pago {payment.name} con lógica SR: {str(e)}")
            return {
                'success': False,
                'payment_name': payment.name,
                'error': str(e)
            }

    def _reconcile_payment_sr_style(self, payment, invoice_move, amount_to_reconcile, original_payment_line):
        """
        Reconcilia un pago parcialmente con una factura usando EXACTAMENTE la lógica de sr_partial_invoice_payment
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            original_payment_line: Línea de pago original
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            # Obtener líneas de factura pendientes de reconciliación
            invoice_lines = invoice_move.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable']
                and not line.reconciled
                and abs(line.amount_residual) > 0
            )
            
            if not invoice_lines:
                _logger.warning(f"No se encontraron líneas de factura pendientes para {invoice_move.name}")
                return False
            
            invoice_line = invoice_lines[0]
            
            # IMPLEMENTACIÓN EXACTA DE sr_partial_invoice_payment
            vals_list = []
            
            # 1. Crear nueva línea de débito en el asiento del pago (igual que SR)
            vals_list.append((0, 0, {
                "account_id": invoice_line.account_id.id,
                "partner_id": invoice_line.partner_id.id,
                "name": invoice_line.name,
                "amount_currency": -amount_to_reconcile,
                "currency_id": invoice_line.currency_id.id if invoice_line.currency_id else payment.currency_id.id,
                "debit": 0.0,
                "credit": amount_to_reconcile,
                "tax_ids": [(6, 0, invoice_line.tax_ids.ids)],
                "date_maturity": invoice_line.date_maturity,
            }))
            
            # 2. Reducir la línea original del pago (igual que SR)
            vals_list.append((1, original_payment_line.id, {
                "debit": 0.0,
                "credit": original_payment_line.credit - amount_to_reconcile,
                "amount_currency": -(original_payment_line.credit - amount_to_reconcile),
            }))
            
            # 3. Aplicar cambios al asiento del pago (igual que SR)
            payment.move_id.write({"line_ids": vals_list})
            
            # 4. Generar número de coincidencia parcial (usando nuestra secuencia)
            partial_sequence = self.env["ir.sequence"].next_by_code("partial.matching.sequence") or ""
            
            # 5. Obtener la nueva línea creada (igual que SR)
            lines = payment.move_id.line_ids.filtered(
                lambda l: l.credit == amount_to_reconcile
                and l.move_id.id == payment.move_id.id
            )
            
            # 6. Asignar partial_matching_number a la nueva línea (igual que SR)
            if lines and not lines[-1].partial_matching_number:
                lines[-1].write({"partial_matching_number": partial_sequence})
            
            # 7. Buscar línea de factura correspondiente (igual que SR)
            if lines:
                move_line = invoice_move.line_ids.filtered(
                    lambda l: l.credit != amount_to_reconcile
                    and l.account_id.id == lines[-1].account_id.id
                    and l.move_id.id == invoice_move.id
                )
                
                # 8. Asignar partial_matching_number a la línea de factura (igual que SR)
                if move_line and not move_line.partial_matching_number:
                    move_line.write({"partial_matching_number": partial_sequence})
                elif move_line and move_line.partial_matching_number:
                    move_line.write({
                        "partial_matching_number": "%s,%s" % (move_line.partial_matching_number, partial_sequence)
                    })
                
                # 9. Reconciliar las líneas con el mismo partial_matching_number (igual que SR)
                lines += move_line
                result = lines.reconcile()
                
                _logger.info(f"✓ Reconciliación parcial SR exitosa con número de coincidencia: {partial_sequence}")
                return True
            
            return False
            
        except Exception as e:
            _logger.error(f"Error en reconciliación parcial SR de pago con factura: {str(e)}")
            return False

    def button_reconciliate_payments_simple(self):
        """
        MÉTODO SIMPLIFICADO: Reconcilia pagos con facturas agregando líneas liability_payable al asiento del pago
        
        Este método:
        1. Toma la primera factura a pagar con monto asignado
        2. Del monto payment_aggregator_total_import, modifica el asiento del pago agregando una nueva línea liability_payable
        3. Asocia esa nueva línea con la factura a pagar
        4. Mantiene el tracking de montos como se hace actualmente
        """
        try:
            _logger.info(f"=== INICIANDO RECONCILIACIÓN SIMPLE PARA AGRUPADOR {self.name} ===")
            
            # Validar que el agrupador esté en estado publicado
            if self.state != 'published':
                raise UserError("El agrupador debe estar en estado 'Publicado' para reconciliar pagos")
            
            # Obtener pagos del agrupador usando búsqueda
            payments = self.env["account.payment"].search([
                ("payment_aggregator_id", "=", self.id),
                ("state", "=", "posted")
            ])
            if not payments:
                raise UserError("No hay pagos confirmados para reconciliar")
            
            _logger.info(f"Pagos encontrados: {len(payments)}")
            
            # Obtener facturas con montos asignados
            invoice_lines = self.account_move_line_payment_agg_ids.filtered(
                lambda l: l.payment_aggregator_total_import > 0
            )
            if not invoice_lines:
                raise UserError("No hay facturas con montos asignados para reconciliar")
            
            _logger.info(f"Facturas a reconciliar: {len(invoice_lines)}")
            
            # Procesar cada pago secuencialmente
            for payment in payments:
                _logger.info(f"=== PROCESANDO PAGO {payment.name} - Monto: {payment.amount} - Moneda: {payment.currency_id.name} ===")
                
                # Obtener facturas restantes para este pago
                remaining_invoices = invoice_lines.filtered(
                    lambda l: l.payment_aggregator_total_import > 0
                )
                
                if not remaining_invoices:
                    _logger.info(f"No hay facturas restantes para el pago {payment.name}")
                    continue
                
                _logger.info(f"Facturas restantes para pago {payment.name}: {len(remaining_invoices)}")
                
                # Distribuir el pago entre las facturas usando el nuevo método
                self._distribute_payment_simple_new(payment, remaining_invoices)
            
            # Actualizar estados de facturas
            self._update_invoice_states()
            
            _logger.info(f"=== RECONCILIACIÓN SIMPLE COMPLETADA PARA AGRUPADOR {self.name} ===")
            
        except Exception as e:
            _logger.error(f"Error en reconciliación simple: {e}")
            raise UserError(f"Error durante la reconciliación simple: {e}")
    
    def _distribute_payment_simple_new(self, payment, remaining_invoices):
        """
        NUEVO MÉTODO: Distribuye un pago agregando líneas liability_payable al asiento del pago
        
        Este método:
        1. Toma la primera factura a pagar con monto asignado
        2. Del monto payment_aggregator_total_import, modifica el asiento del pago agregando una nueva línea liability_payable
        3. Asocia esa nueva línea con la factura a pagar
        4. Mantiene el tracking de montos como se hace actualmente
        
        Args:
            payment: Pago a distribuir
            remaining_invoices: Facturas restantes por reconciliar
        """
        try:
            _logger.info(f"Distribuyendo pago {payment.name} agregando líneas liability_payable al asiento")
            
            # Obtener la primera factura a pagar (ordenada por ID para consistencia)
            first_invoice_line = remaining_invoices.sorted('id')[0]
            invoice_move = first_invoice_line.move_id
            amount_to_pay = first_invoice_line.payment_aggregator_total_import
            
            _logger.info(f"Primera factura a pagar: {invoice_move.name} - Monto: {amount_to_pay}")
            
            # Verificar que el asiento del pago no esté bloqueado
            if payment.move_id.state != 'posted':
                _logger.error(f"El asiento del pago {payment.name} no está confirmado (estado: {payment.move_id.state})")
                return
            
            # Verificar que la factura esté en estado válido
            if invoice_move.state not in ['posted', 'draft']:
                _logger.error(f"La factura {invoice_move.name} no está en estado válido (estado: {invoice_move.state})")
                return
            
            # Verificar que el pago tenga saldo suficiente
            payment_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and abs(l.amount_residual) > 0
            )
            
            if not payment_lines:
                _logger.warning(f"No hay líneas de pago con saldo residual para {payment.name}")
                return
            
            available_payment_amount = abs(payment_lines[0].amount_residual)
            if available_payment_amount < amount_to_pay:
                _logger.warning(f"Pago {payment.name} no tiene saldo suficiente. Disponible: {available_payment_amount}, Necesario: {amount_to_pay}")
                amount_to_pay = available_payment_amount
            
            # Obtener la cuenta de la factura para la nueva línea
            if invoice_move.move_type in ['out_invoice', 'out_refund']:
                # Factura de venta - buscar cuenta por cobrar
                account_type_to_find = 'asset_receivable'
            else:
                # Factura de compra - buscar cuenta por pagar
                account_type_to_find = 'liability_payable'
            
            invoice_account_lines = invoice_move.line_ids.filtered(
                lambda l: l.account_id.account_type == account_type_to_find
                and abs(l.amount_residual) > 0
            )
            
            if not invoice_account_lines:
                _logger.error(f"No se encontró línea {account_type_to_find} en la factura {invoice_move.name}")
                return
            
            if len(invoice_account_lines) > 1:
                _logger.warning(f"Se encontraron múltiples líneas {account_type_to_find} en la factura {invoice_move.name}, usando la primera")
            
            invoice_account = invoice_account_lines[0].account_id
            _logger.info(f"Cuenta de la factura para nueva línea: {invoice_account.name} (tipo: {invoice_account.account_type})")
            
            # Usar el monto que realmente necesitamos reconciliar (amount_to_pay)
            # Este es el monto de payment_aggregator_total_import de la factura
            line_amount = amount_to_pay
            currency_amount = amount_to_pay

            # Poner el asiento en borrador para poder modificarlo
            payment.move_id.button_draft()

            # Encontrar la línea de crédito existente (cuenta por cobrar/pagar)
            credit_line = payment.move_id.line_ids.filtered(
                lambda l: l.credit > 0 and l.account_id.account_type in ['asset_receivable', 'liability_payable']
            )
            
            if not credit_line:
                _logger.error(f"No se encontró línea de crédito válida en el asiento")
                return
            
            if len(credit_line) > 1:
                _logger.warning(f"Se encontraron múltiples líneas de crédito en el asiento, usando la primera")
            
            credit_line = credit_line[0]
            _logger.info(f"Línea crédito original: {credit_line.account_id.name} - Monto: {credit_line.credit} - Amount Currency: {credit_line.amount_currency}")
            
            # Usar el patrón de vals_list como en sr_partial_invoice_payment
            vals_list = []
            
            # 1. Crear nueva línea de crédito - cuenta de la factura
            vals_list.append((0, 0, {
                'account_id': invoice_account.id,
                'partner_id': payment.partner_id.id,
                'name': f'Pago a {invoice_move.name}',
                'amount_currency': -amount_to_pay,  # Negativo para crédito
                'currency_id': payment.currency_id.id,
                'debit': 0.0,
                'credit': amount_to_pay,
                'date_maturity': payment.date,
                'ref': f'Reconciliación automática - {payment.name}',
            }))
            
            # 2. Ajustar línea de crédito existente - reducir el monto
            vals_list.append((1, credit_line.id, {
                'debit': 0.0,
                'credit': credit_line.credit - amount_to_pay,
                'amount_currency': credit_line.amount_currency - amount_to_pay,
            }))
            
            # Aplicar cambios usando el patrón de sr_partial_invoice_payment
            payment.move_id.write({'line_ids': vals_list})
            _logger.info(f"Líneas del asiento actualizadas - Nueva línea creada y línea existente ajustada")
            
            # Generar número de secuencia para tracking (patrón de sr_partial_invoice_payment)
            partial_sequence = self.env["ir.sequence"].next_by_code("account.move.line") or f"PM{self.env.cr.dbname}{self.env.uid}"
            
            # Volver a confirmar el asiento después de los cambios
            payment.move_id.action_post()
            _logger.info(f"Asiento confirmado después de los cambios: {payment.move_id.name}")
            
            # Obtener la nueva línea creada para la reconciliación
            _logger.info(f"Buscando nueva línea con criterios: credit={amount_to_pay}, account_id={invoice_account.id}, name='Pago a {invoice_move.name}'")
            
            # Listar todas las líneas del asiento para debugging
            all_lines = payment.move_id.line_ids
            _logger.info(f"Total de líneas en el asiento: {len(all_lines)}")
            for i, line in enumerate(all_lines):
                _logger.info(f"Línea {i}: ID={line.id}, Account={line.account_id.name}, Credit={line.credit}, Debit={line.debit}, Name='{line.name}'")
            
            # Buscar la nueva línea con criterios más flexibles
            new_lines = payment.move_id.line_ids.filtered(
                lambda l: l.credit == amount_to_pay 
                and l.account_id == invoice_account 
                and f'Pago a {invoice_move.name}' in l.name
            )
            
            _logger.info(f"Líneas encontradas con criterios específicos: {len(new_lines)}")
            
            if not new_lines:
                _logger.warning(f"No se encontró la nueva línea con criterios específicos, intentando búsqueda más amplia")
                # Intentar búsqueda más amplia - cualquier línea de crédito con la cuenta correcta
                fallback_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id == invoice_account and l.credit > 0
                )
                _logger.info(f"Líneas de fallback encontradas: {len(fallback_lines)}")
                
                if fallback_lines:
                    # Buscar la línea que no sea la original (que ya fue ajustada)
                    for line in fallback_lines:
                        if line.id != credit_line.id:
                            new_line = line
                            _logger.info(f"Usando línea de fallback: {new_line.id} - Cuenta: {new_line.account_id.name} - Credit: {new_line.credit}")
                            break
                    else:
                        _logger.error(f"No se encontró línea válida para reconciliación")
                        return
                else:
                    _logger.error(f"No se encontró ninguna línea de crédito con la cuenta {invoice_account.name}")
                    return
            else:
                new_line = new_lines[0]
                _logger.info(f"Nueva línea encontrada para reconciliación: {new_line.id} - Cuenta: {new_line.account_id.name}")
            
            # Asignar número de matching a la nueva línea
            try:
                new_line.write({"partial_matching_number": partial_sequence})
                _logger.info(f"Número de matching asignado a nueva línea: {partial_sequence}")
            except Exception as e:
                _logger.warning(f"No se pudo asignar número de matching: {e}")
                # Continuar sin el número de matching
            
            # Reconcilia la nueva línea del pago con la línea de la factura
            try:
                # Obtener la línea de la factura para reconciliar
                if invoice_move.move_type in ['out_invoice', 'out_refund']:
                    # Factura de venta - buscar cuenta por cobrar
                    account_type_to_find = 'asset_receivable'
                else:
                    # Factura de compra - buscar cuenta por pagar
                    account_type_to_find = 'liability_payable'
                
                invoice_account_lines = invoice_move.line_ids.filtered(
                    lambda l: l.account_id.account_type == account_type_to_find
                    and abs(l.amount_residual) > 0
                )
                
                if not invoice_account_lines:
                    _logger.error(f"No se encontró línea {account_type_to_find} en la factura {invoice_move.name}")
                    return
                
                invoice_line_to_reconcile = invoice_account_lines[0]
                
                # Asignar número de matching a la línea de la factura (patrón sr_partial_invoice_payment)
                if not invoice_line_to_reconcile.partial_matching_number:
                    invoice_line_to_reconcile.write({"partial_matching_number": partial_sequence})
                else:
                    invoice_line_to_reconcile.write({
                        "partial_matching_number": f"{invoice_line_to_reconcile.partial_matching_number},{partial_sequence}"
                    })
                
                # Realizar la reconciliación usando el patrón de sr_partial_invoice_payment
                lines_to_reconcile = new_line + invoice_line_to_reconcile
                result = lines_to_reconcile.reconcile()
                
                _logger.info(f"✓ Reconciliación exitosa: {amount_to_pay} entre pago {payment.name} y factura {invoice_move.name}")
                
                # Actualizar el monto asignado a la factura
                first_invoice_line.payment_aggregator_total_import -= amount_to_pay
                
                # Actualizar el saldo residual del pago (esto se hace automáticamente por Odoo)
                payment.move_id._compute_amount()
                
                _logger.info(f"Monto restante de la factura {invoice_move.name}: {first_invoice_line.payment_aggregator_total_import}")
                
            except Exception as reconcile_error:
                _logger.error(f"Error en reconciliación: {reconcile_error}")
                # Si falla la reconciliación, eliminar la línea creada y restaurar la línea original
                new_line.unlink()
                # Restaurar la línea original del pago
                return False
            
        except Exception as e:
            _logger.error(f"Error distribuyendo pago {payment.name}: {e}")
            raise

    def _distribute_payment_simple(self, payment, remaining_invoices):
        """
        Distribuye un pago entre las facturas restantes usando asientos de ajuste
        
        Args:
            payment: Pago a distribuir
            remaining_invoices: Facturas restantes por reconciliar
        """
        try:
            _logger.info(f"Distribuyendo pago {payment.name} usando asientos de ajuste")
            
            # Obtener líneas de pago con saldo residual
            payment_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and abs(l.amount_residual) > 0
            )
            
            if not payment_lines:
                _logger.warning(f"No hay líneas de pago con saldo residual para {payment.name}")
                return
            
            _logger.info(f"Líneas de pago pendientes: {len(payment_lines)}")
            
            # Procesar cada factura secuencialmente
            for invoice_line in remaining_invoices:
                if payment_lines[0].amount_residual == 0:
                    _logger.info(f"Pago {payment.name} agotado")
                    break
                
                amount_to_reconcile = min(
                    abs(payment_lines[0].amount_residual),
                    invoice_line.payment_aggregator_total_import
                )
                
                if amount_to_reconcile <= 0:
                    continue
                
                _logger.info(f"Reconciliando {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                
                # Crear asiento de ajuste y reconciliar
                success = self._create_adjustment_and_reconcile_simple(
                    payment, 
                    invoice_line.move_id,  # Usar move_id en lugar de invoice_id
                    amount_to_reconcile
                )
                
                if success:
                    # Actualizar el monto asignado a la factura
                    invoice_line.payment_aggregator_total_import -= amount_to_reconcile
                    _logger.info(f"✓ Reconciliado {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
                else:
                    _logger.warning(f"✗ Falló reconciliación de {amount_to_reconcile} del pago {payment.name} con factura {invoice_line.move_id.name}")
            
            # Verificar si quedó saldo sin reconciliar
            remaining_amount = abs(payment_lines[0].amount_residual)
            if remaining_amount > 0:
                _logger.warning(f"Pago {payment.name}: Falta reconciliar {remaining_amount}")
            
        except Exception as e:
            _logger.error(f"Error distribuyendo pago {payment.name}: {e}")
            raise
    
    def _create_adjustment_and_reconcile_simple(self, payment, invoice_move, amount_to_reconcile):
        """
        Crea un asiento de ajuste y reconcilia entre el pago y la factura
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            _logger.info(f"Creando asiento de ajuste para reconciliar {amount_to_reconcile}")
            
            # Obtener líneas de pago y factura
            payment_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and abs(l.amount_residual) > 0
            )
            
            invoice_lines = invoice_move.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and abs(l.amount_residual) > 0
            )
            
            if not payment_lines or not invoice_lines:
                _logger.warning("No se encontraron líneas válidas para reconciliar")
                return False
            
            # Crear asiento de ajuste
            adjustment_move = self._create_simple_adjustment_entry(
                payment, invoice_move, amount_to_reconcile
            )
            
            if not adjustment_move:
                return False
            
            # Reconcilia las líneas usando el asiento de ajuste
            return self._reconcile_with_adjustment_simple(
                payment_lines[0], invoice_lines[0], adjustment_move, amount_to_reconcile
            )
            
        except Exception as e:
            _logger.error(f"Error creando asiento de ajuste: {e}")
            return False
    
    def _create_simple_adjustment_entry(self, payment, invoice_move, amount_to_reconcile):
        """
        Crea un asiento de ajuste simple para reconciliar entre cuentas diferentes
        
        Args:
            payment: Pago a reconciliar
            invoice_move: Factura a reconciliar
            amount_to_reconcile: Monto a reconciliar
            
        Returns:
            account.move: Asiento de ajuste creado
        """
        try:
            # Obtener cuentas
            payment_account = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
            )[0].account_id
            
            invoice_account = invoice_move.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
            )[0].account_id
            
            # Crear asiento de ajuste
            adjustment_vals = {
                'move_type': 'entry',
                'date': payment.date,
                'ref': f'Ajuste para reconciliación {payment.name} - {invoice_move.name}',
                'line_ids': [
                    # Línea de débito (cuenta de pago)
                    (0, 0, {
                        'account_id': payment_account.id,
                        'debit': amount_to_reconcile,
                        'credit': 0,
                        'currency_id': payment.currency_id.id,
                        'amount_currency': amount_to_reconcile,
                    }),
                    # Línea de crédito (cuenta de factura)
                    (0, 0, {
                        'account_id': invoice_account.id,
                        'debit': 0,
                        'credit': amount_to_reconcile,
                        'currency_id': payment.currency_id.id,
                        'amount_currency': -amount_to_reconcile,
                    }),
                ]
            }
            
            adjustment_move = self.env['account.move'].create(adjustment_vals)
            adjustment_move.action_post()
            
            _logger.info(f"Asiento de ajuste creado: {adjustment_move.name}")
            return adjustment_move
            
        except Exception as e:
            _logger.error(f"Error creando asiento de ajuste: {e}")
            return None
    
    def _reconcile_with_adjustment_simple(self, payment_line, invoice_line, adjustment_move, amount):
        """
        Reconcilia las líneas usando el asiento de ajuste como puente
        
        Args:
            payment_line: Línea del pago
            invoice_line: Línea de la factura
            adjustment_move: Asiento de ajuste
            amount: Monto a reconciliar
            
        Returns:
            bool: True si la reconciliación fue exitosa
        """
        try:
            # Obtener líneas del asiento de ajuste
            adjustment_lines = adjustment_move.line_ids
            
            # Reconcilia pago con línea de débito del ajuste
            payment_adjustment_lines = adjustment_lines.filtered(
                lambda l: l.account_id == payment_line.account_id
            )
            
            if payment_adjustment_lines:
                (payment_line | payment_adjustment_lines[0]).reconcile()
                _logger.info("Reconciliación pago-ajuste exitosa")
            
            # Reconcilia factura con línea de crédito del ajuste
            invoice_adjustment_lines = adjustment_lines.filtered(
                lambda l: l.account_id == invoice_line.account_id
            )
            
            if invoice_adjustment_lines:
                (invoice_line | invoice_adjustment_lines[0]).reconcile()
                _logger.info("Reconciliación factura-ajuste exitosa")
            
            return True
            
        except Exception as e:
            _logger.error(f"Error en reconciliación con ajuste: {e}")
            return False

    def _update_invoice_states(self):
        # Actualizar estados de facturas (usar método existente)
        for invoice_line in self.account_move_line_payment_agg_ids:
            if invoice_line.move_id:
                invoice_line.move_id._compute_amount()
                _logger.info(f"Estado de pago actualizado para factura {invoice_line.move_id.name}: {invoice_line.move_id.payment_state}")

    def button_reconciliate_payments_advanced(self):
        """
        Método avanzado de reconciliación que:
        1. Genera un pago por cada factura usando el diario intermedio de la moneda del agrupador
        2. Crea un pago inverso del tipo del talonario por el total de las facturas
        3. Reconcilia contra los métodos de pago del agrupador
        
        Returns:
            dict: Acción de ventana con los pagos creados
        """
        _logger.info(f"=== INICIANDO RECONCILIACIÓN AVANZADA PARA AGRUPADOR {self.name} ===")
        
        try:
            # Validar estado del agrupador
            if self.state != 'published':
                raise UserError(_("El agrupador debe estar en estado 'Publicado' para realizar la reconciliación avanzada"))
            
            # Obtener facturas a reconciliar
            invoice_lines = self.account_move_line_payment_agg_ids.filtered(
                lambda l: l.payment_aggregator_total_import > 0 and l.move_id
            )
            
            if not invoice_lines:
                raise UserError(_("No hay facturas con monto asignado para reconciliar"))
            
            _logger.info(f"Facturas a reconciliar: {len(invoice_lines)}")
            
            # Crear pagos por cada factura
            created_payments = self._create_invoice_payments(invoice_lines)
            
            # Crear pago inverso
            reverse_payment = self._create_reverse_payment(invoice_lines)
            
            # Reconciliar pagos creados con métodos de pago del agrupador
            self._reconcile_with_payment_methods(created_payments + [reverse_payment])
            
            _logger.info(f"=== RECONCILIACIÓN AVANZADA COMPLETADA ===")
            
            # Retornar vista de los pagos creados
            return {
                'type': 'ir.actions.act_window',
                'name': _('Pagos Creados'),
                'res_model': 'account.payment',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', [p.id for p in created_payments + [reverse_payment]])],
                'context': {'create': False}
            }
            
        except Exception as e:
            _logger.error(f"Error en reconciliación avanzada: {e}")
            raise UserError(_(f"Error durante la reconciliación avanzada: {str(e)}"))

    def _create_invoice_payments(self, invoice_lines):
        """
        Crea un pago por cada factura usando el diario intermedio correspondiente a la moneda.
        
        Args:
            invoice_lines: Líneas de facturas a pagar
            
        Returns:
            list: Lista de pagos creados
        """
        created_payments = []
        
        for invoice_line in invoice_lines:
            try:
                invoice = invoice_line.move_id
                amount = invoice_line.payment_aggregator_total_import
                currency = invoice.currency_id
                
                _logger.info(f"Creando pago para factura {invoice.name} - Monto: {amount} - Moneda: {currency.name}")
                
                # Buscar diario intermedio para la moneda de la factura
                intermediate_journal = self._get_intermediate_journal_for_currency(currency)
                
                if not intermediate_journal:
                    _logger.warning(f"No se encontró diario intermedio para moneda {currency.name}, usando diario del agrupador")
                    intermediate_journal = self.account_journal_aggregator_id.account_journal_id
                
                # Determinar tipo de pago basado en el TALONARIO, no en la factura
                # Esto es clave para que funcione correctamente
                if self.receiptbook_id.partner_type == 'customer':
                    # LÓGICA PARA CLIENTES (mantener funcionando)
                    if invoice.move_type in ['out_invoice', 'out_refund']:
                        payment_type = 'inbound'  # Recibimos dinero del cliente
                        partner_type = 'customer'
                    else:
                        payment_type = 'outbound'  # Pagamos al proveedor
                        partner_type = 'supplier'
                else:
                    # LÓGICA PARA PROVEEDORES (nueva implementación)
                    if self.receiptbook_id.type == 'outbound':
                        payment_type = 'outbound'  # Pagamos al proveedor
                        partner_type = 'supplier'
                    else:
                        payment_type = 'inbound'  # Recibimos del proveedor
                        partner_type = 'supplier'
                
                # Determinar el diario correcto según el tipo del talonario
                if self.receiptbook_id.partner_type == 'customer':
                    # Para clientes: usar diario intermedio (lógica existente)
                    payment_journal = intermediate_journal
                    _logger.info(f"Usando diario intermedio para cliente: {payment_journal.name}")
                else:
                    # Para proveedores: usar diario del talonario
                    payment_journal = self.receiptbook_id.account_journal_id
                    _logger.info(f"Usando diario del talonario para proveedor: {payment_journal.name}")

                # Buscar método de pago apropiado para el diario correcto
                if payment_type == 'inbound':
                    method_line = intermediate_journal.inbound_payment_method_line_ids.filtered(
                        lambda m: m.payment_method_id.code == 'manual'
                    )[:1] or intermediate_journal.inbound_payment_method_line_ids[:1]
                else:
                    method_line = intermediate_journal.outbound_payment_method_line_ids.filtered(
                        lambda m: m.payment_method_id.code == 'manual'
                    )[:1] or intermediate_journal.outbound_payment_method_line_ids[:1]
                
                # Crear pago
                payment_vals = {
                    'payment_type': payment_type,
                    'partner_type': partner_type,
                    'partner_id': invoice.partner_id.id,
                    'amount': amount,
                    'currency_id': currency.id,
                    'journal_id': intermediate_journal.id,
                    'date': self.date,  # Fecha del agrupador
                    'ref': f'Pago automático - {invoice.name}',
                    'payment_method_line_id': method_line.id if method_line else False,
                    'payment_aggregator_id': self.id,
                }
                
                payment = self.env['account.payment'].create(payment_vals)
                payment.action_post()
                
                # Para proveedores, modificar el asiento para usar las cuentas correctas del campo "pago a cuenta"
                if self.receiptbook_id.partner_type == 'supplier':
                    _logger.info(f"Modificando asiento del pago para proveedor usando cuentas del campo pago a cuenta")

                    # Buscar la cuenta correcta según la moneda en el diario del talonario
                    # El diario del talonario tiene configuradas las cuentas por moneda en account_currency_ids
                    if hasattr(payment_journal, 'account_currency_ids'):
                        currency_account = payment_journal.account_currency_ids.filtered(
                            lambda c: c.currency_id.id == currency.id
                        )[:1]

                        if currency_account:
                            _logger.info(f"Usando cuenta específica para moneda {currency.name}: {currency_account.account_id.name} ({currency_account.account_id.account_type})")

                            # Modificar la línea del asiento que tiene el partner
                            payment_move = payment.move_id
                            partner_lines = payment_move.line_ids.filtered(
                                lambda l: l.partner_id == invoice.partner_id and l.account_id.account_type in ['asset_receivable', 'liability_payable']
                            )

                            if partner_lines:
                                partner_lines[0].write({
                                    'account_id': currency_account.account_id.id,
                                })
                                _logger.info(f"Línea modificada: {partner_lines[0].account_id.name} ({partner_lines[0].account_id.account_type})")
                        else:
                            _logger.warning(f"No se encontró cuenta específica para moneda {currency.name} en el diario del talonario")

                # Asociar el pago a la factura correspondiente
                try:
                    _logger.info(f"Intentando reconciliar pago {payment.name} con factura {invoice.name}")
                    
                    # Buscar las líneas de la factura que coincidan con el pago
                    invoice_lines = invoice.line_ids.filtered(
                        lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                        and l.amount_residual != 0
                    )
                    
                    # Buscar las líneas del pago que coincidan
                    payment_lines = payment.move_id.line_ids.filtered(
                        lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                    )
                    
                    _logger.info(f"Líneas de factura encontradas: {len(invoice_lines)}")
                    _logger.info(f"Líneas de pago encontradas: {len(payment_lines)}")
                    
                    # Reconciliar las líneas compatibles
                    if invoice_lines and payment_lines:
                        # Buscar líneas compatibles por partner (más flexible)
                        for invoice_line in invoice_lines:
                            _logger.info(f"Buscando línea compatible para factura: {invoice_line.account_id.name} - Partner: {invoice_line.partner_id.name}")
                            
                            # Primero intentar por cuenta exacta y partner
                            compatible_payment_line = payment_lines.filtered(
                                lambda l: l.account_id == invoice_line.account_id 
                                and l.partner_id == invoice_line.partner_id
                            )
                            
                            # Si no encuentra, intentar solo por partner y tipo de cuenta
                            if not compatible_payment_line:
                                compatible_payment_line = payment_lines.filtered(
                                    lambda l: l.account_id.account_type == invoice_line.account_id.account_type
                                    and l.partner_id == invoice_line.partner_id
                                )
                            
                            _logger.info(f"Líneas compatibles encontradas: {len(compatible_payment_line)}")
                            
                            if compatible_payment_line:
                                try:
                                    # Verificar que las líneas tengan montos compatibles
                                    invoice_amount = abs(invoice_line.amount_residual)
                                    payment_amount = abs(compatible_payment_line[0].balance)
                                    
                                    _logger.info(f"Monto factura: {invoice_amount}, Monto pago: {payment_amount}")
                                    
                                    if invoice_amount > 0 and payment_amount > 0:
                                        (invoice_line | compatible_payment_line[0]).reconcile()
                                        _logger.info(f"✓ Pago {payment.name} reconciliado con factura {invoice.name}")
                                        break
                                    else:
                                        _logger.warning(f"Montos no compatibles para reconciliación: factura={invoice_amount}, pago={payment_amount}")
                                except Exception as e:
                                    _logger.warning(f"No se pudo reconciliar pago {payment.name} con factura {invoice.name}: {e}")
                            else:
                                _logger.warning(f"No se encontraron líneas compatibles para factura {invoice.name}")
                    else:
                        _logger.warning(f"No hay líneas para reconciliar: factura={len(invoice_lines)}, pago={len(payment_lines)}")
                    
                except Exception as e:
                    _logger.warning(f"Error asociando pago {payment.name} a factura {invoice.name}: {e}")
                
                created_payments.append(payment)
                _logger.info(f"✓ Pago creado: {payment.name} - Monto: {amount} - Moneda: {currency.name}")
                
            except Exception as e:
                _logger.error(f"Error creando pago para factura {invoice_line.move_id.name}: {e}")
                continue
        
        return created_payments

    def _get_intermediate_journal_for_currency(self, currency):
        """
        Busca el diario intermedio para una moneda específica.
        
        Args:
            currency: Moneda para la cual buscar el diario
            
        Returns:
            account.journal: Diario intermedio encontrado o None
        """
        journal_aggregator = self.env['account.journal.aggregator'].search([
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', currency.id)
        ], limit=1)
        
        if journal_aggregator:
            return journal_aggregator.account_journal_id
        
        return None

    def _create_reverse_payment(self, invoice_lines):
        """
        Crea un pago inverso del tipo del talonario por el total de las facturas.
        
        Args:
            invoice_lines: Líneas de facturas que se están pagando
            
        Returns:
            account.payment: Pago inverso creado
        """
        try:
            # Calcular total de las facturas
            total_amount = sum(invoice_lines.mapped('payment_aggregator_total_import'))
            
            _logger.info(f"Creando pago inverso por monto total: {total_amount}")
            
            # Determinar tipo de pago inverso basado en el talonario
            receiptbook = self.receiptbook_id
            if receiptbook.type == 'inbound':
                reverse_payment_type = 'outbound'  # Si el talonario es entrante, el inverso es saliente
            else:
                reverse_payment_type = 'inbound'  # Si el talonario es saliente, el inverso es entrante
            
            # Usar el mismo partner_type que el talonario
            partner_type = receiptbook.partner_type
            
            # Usar el diario intermedio del agrupador (no el del talonario)
            intermediate_journal = self.account_journal_aggregator_id.account_journal_id
            
            # Buscar método de pago apropiado para el pago inverso en el diario intermedio
            if reverse_payment_type == 'inbound':
                method_line = intermediate_journal.inbound_payment_method_line_ids.filtered(
                    lambda m: m.payment_method_id.code == 'manual'
                )[:1] or intermediate_journal.inbound_payment_method_line_ids[:1]
            else:
                method_line = intermediate_journal.outbound_payment_method_line_ids.filtered(
                    lambda m: m.payment_method_id.code == 'manual'
                )[:1] or intermediate_journal.outbound_payment_method_line_ids[:1]
            
            # Crear pago inverso
            reverse_payment_vals = {
                'payment_type': reverse_payment_type,
                'partner_type': partner_type,
                'partner_id': self.customer_id.id,
                'amount': total_amount,
                'currency_id': self.currency_id.id,
                'journal_id': intermediate_journal.id,  # Diario intermedio, no el del talonario
                'date': self.date,  # Fecha del agrupador
                'ref': f'Pago inverso - {self.name}',
                'payment_method_line_id': method_line.id if method_line else False,
                'payment_aggregator_id': self.id,
            }
            
            # Agregar tipo de documento si está disponible en el talonario
            if receiptbook.document_type_id:
                reverse_payment_vals['l10n_latam_document_type_id'] = receiptbook.document_type_id.id
            else:
                # Buscar un tipo de documento por defecto para el diario
                default_doc_type = self._get_default_document_type(receiptbook.account_journal_id)
                if default_doc_type:
                    reverse_payment_vals['l10n_latam_document_type_id'] = default_doc_type.id
                    _logger.info(f"Usando tipo de documento por defecto: {default_doc_type.name}")
                else:
                    _logger.warning("No se encontró tipo de documento para el pago inverso")
            
            reverse_payment = self.env['account.payment'].create(reverse_payment_vals)
            reverse_payment.action_post()
            
            _logger.info(f"✓ Pago inverso creado: {reverse_payment.name} - Monto: {total_amount}")
            
            return reverse_payment
            
        except Exception as e:
            _logger.error(f"Error creando pago inverso: {e}")
            raise

    def _reconcile_with_payment_methods(self, payments):
        """
        Reconcilia los pagos creados con los métodos de pago del agrupador.
        
        Args:
            payments: Lista de pagos a reconciliar
        """
        try:
            _logger.info(f"Reconciliando {len(payments)} pagos con métodos de pago del agrupador")
            
            # Obtener SOLO los pagos generados por los métodos de pago del agrupador
            # Excluir los pagos de facturas que se crearon en esta misma operación
            existing_payments = self.env['account.payment'].search([
                ('payment_aggregator_id', '=', self.id),
                ('state', '=', 'posted'),
                ('ref', 'not ilike', 'Pago automático'),  # Excluir pagos de facturas
                ('ref', 'not ilike', 'Pago inverso'),     # Excluir pago inverso
            ])
            
            if not existing_payments:
                _logger.warning("No hay pagos existentes del agrupador para reconciliar")
                return
            
            _logger.info(f"Pagos de métodos de pago del agrupador encontrados: {len(existing_payments)}")
            for payment in existing_payments:
                _logger.info(f"  - {payment.name}: {payment.ref}")
            
            # Crear líneas de reconciliación de los pagos creados
            new_payment_lines = self.env['account.move.line']
            for payment in payments:
                # Buscar líneas de débito en el pago (cuentas por cobrar/pagar)
                payment_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                )
                new_payment_lines |= payment_lines
            
            # Crear líneas de reconciliación de los pagos existentes
            existing_payment_lines = self.env['account.move.line']
            for payment in existing_payments:
                # Buscar líneas de crédito en los pagos existentes
                payment_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                )
                existing_payment_lines |= payment_lines
            
            _logger.info(f"Líneas de pagos nuevos: {len(new_payment_lines)}")
            _logger.info(f"Líneas de pagos existentes: {len(existing_payment_lines)}")
            
            # Separar el pago inverso de los pagos individuales
            reverse_payment = None
            individual_payment_lines = self.env['account.move.line']
            
            for payment in payments:
                if 'Pago inverso' in payment.ref:
                    reverse_payment = payment
                else:
                    # Los pagos individuales ya se reconciliaron con sus facturas
                    payment_lines = payment.move_id.line_ids.filtered(
                        lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                    )
                    individual_payment_lines |= payment_lines
            
            _logger.info(f"Pago inverso: {reverse_payment.name if reverse_payment else 'No encontrado'}")
            _logger.info(f"Pagos individuales: {len(individual_payment_lines)}")
            
            # Reconciliar el pago inverso contra los métodos de pago del agrupador
            reconciled_count = 0
            if reverse_payment:
                reconciled_count += self._reconcile_reverse_payment_with_methods(reverse_payment, existing_payments)
            
            # Los pagos individuales ya se reconciliaron con sus facturas correspondientes
            _logger.info("Pagos individuales ya reconciliados con sus facturas")
            
            _logger.info(f"Reconciliación completada: {reconciled_count} líneas reconciliadas")
            
        except Exception as e:
            _logger.error(f"Error reconciliando con métodos de pago: {e}")
            raise
    
    def _reconcile_reverse_payment_with_methods(self, reverse_payment, existing_payments):
        """
        Reconcilia el pago inverso SOLO con los métodos de pago del agrupador (NO con pagos de facturas).
        
        Args:
            reverse_payment: Pago inverso a reconciliar
            existing_payments: Pagos de métodos de pago del agrupador (NO pagos de facturas)
            
        Returns:
            int: Número de líneas reconciliadas
        """
        try:
            _logger.info(f"Reconciliando pago inverso {reverse_payment.name} SOLO con métodos de pago del agrupador")
            _logger.info(f"Pagos de métodos de pago disponibles: {len(existing_payments)}")
            
            # Obtener líneas del pago inverso
            reverse_payment_lines = reverse_payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and l.amount_residual != 0
            )
            
            # Obtener líneas SOLO de los métodos de pago del agrupador
            existing_payment_lines = self.env['account.move.line']
            for payment in existing_payments:
                _logger.info(f"Procesando pago de método: {payment.name} - {payment.ref}")
                payment_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                    and l.amount_residual != 0
                )
                existing_payment_lines |= payment_lines
                _logger.info(f"  Líneas encontradas: {len(payment_lines)}")
            
            _logger.info(f"Líneas del pago inverso: {len(reverse_payment_lines)}")
            _logger.info(f"Líneas de métodos de pago: {len(existing_payment_lines)}")
            
            if not existing_payment_lines:
                _logger.warning("No hay líneas de métodos de pago para reconciliar")
                return 0
            
            # Combinar todas las líneas para reconciliación masiva
            all_lines_to_reconcile = reverse_payment_lines | existing_payment_lines
            
            _logger.info(f"Total de líneas a reconciliar juntas: {len(all_lines_to_reconcile)}")
            
            if len(all_lines_to_reconcile) > 1:
                try:
                    # Reconciliar TODAS las líneas juntas en una sola operación
                    all_lines_to_reconcile.reconcile()
                    _logger.info(f"✓ Reconciliación masiva exitosa: {len(all_lines_to_reconcile)} líneas reconciliadas juntas")
                    return len(all_lines_to_reconcile)
                except Exception as e:
                    _logger.warning(f"No se pudo realizar reconciliación masiva: {e}")
                    
                    # Fallback: intentar reconciliación por grupos compatibles
                    return self._reconcile_by_compatible_groups(reverse_payment_lines, existing_payment_lines)
            else:
                _logger.warning("No hay suficientes líneas para reconciliar")
                return 0
            
        except Exception as e:
            _logger.error(f"Error reconciliando pago inverso: {e}")
            return 0
    
    def _reconcile_by_compatible_groups(self, reverse_lines, existing_lines):
        """
        Reconciliación por grupos compatibles como fallback.
        
        Args:
            reverse_lines: Líneas del pago inverso
            existing_lines: Líneas de métodos de pago
            
        Returns:
            int: Número de líneas reconciliadas
        """
        try:
            _logger.info("Intentando reconciliación por grupos compatibles")
            reconciled_count = 0
            
            for reverse_line in reverse_lines:
                _logger.info(f"Buscando grupo compatible para: {reverse_line.account_id.name} - Partner: {reverse_line.partner_id.name}")
                
                # Buscar líneas compatibles por cuenta y partner
                compatible_lines = existing_lines.filtered(
                    lambda l: l.account_id == reverse_line.account_id 
                    and l.partner_id == reverse_line.partner_id
                    and l.amount_residual != 0
                )
                
                # Si no encuentra por cuenta exacta, buscar por tipo de cuenta
                if not compatible_lines:
                    compatible_lines = existing_lines.filtered(
                        lambda l: l.account_id.account_type == reverse_line.account_id.account_type
                        and l.partner_id == reverse_line.partner_id
                        and l.amount_residual != 0
                    )
                
                if compatible_lines:
                    try:
                        # Reconciliar el grupo compatible
                        group_to_reconcile = reverse_line | compatible_lines
                        group_to_reconcile.reconcile()
                        reconciled_count += len(group_to_reconcile)
                        _logger.info(f"✓ Grupo reconciliado: {len(group_to_reconcile)} líneas")
                        
                        # Remover las líneas ya reconciliadas
                        existing_lines -= compatible_lines
                    except Exception as e:
                        _logger.warning(f"No se pudo reconciliar grupo: {e}")
            
            return reconciled_count
            
        except Exception as e:
            _logger.error(f"Error en reconciliación por grupos: {e}")
            return 0

    def _get_default_document_type(self, journal):
        """
        Busca un tipo de documento por defecto para un diario específico.
        
        Args:
            journal: Diario para el cual buscar el tipo de documento
            
        Returns:
            l10n_latam.document.type: Tipo de documento encontrado o None
        """
        try:
            # Buscar tipos de documento activos para el diario
            doc_types = self.env['l10n_latam.document.type'].search([
                ('active', '=', True),
                ('journal_ids', 'in', [journal.id])
            ], limit=1)
            
            if doc_types:
                return doc_types[0]
            
            # Si no se encuentra específico para el diario, buscar uno genérico
            generic_doc_types = self.env['l10n_latam.document.type'].search([
                ('active', '=', True),
                ('internal_type', '=', 'payment')
            ], limit=1)
            
            if generic_doc_types:
                return generic_doc_types[0]
            
            return None
            
        except Exception as e:
            _logger.warning(f"Error buscando tipo de documento por defecto: {e}")
            return None

    def _modify_payment_account_for_supplier(self, payment, currency, payment_journal):
        """
        Modifica el asiento del pago para usar las cuentas correctas del campo "pago a cuenta"
        según la moneda específica
        """
        try:
            _logger.info(f"Modificando asiento del pago para proveedor usando cuentas del campo pago a cuenta")

            # Buscar la cuenta correcta según la moneda en el diario del talonario
            # El diario del talonario tiene configuradas las cuentas por moneda en account_currency_ids
            if hasattr(payment_journal, 'account_currency_ids'):
                currency_account = payment_journal.account_currency_ids.filtered(
                    lambda c: c.currency_id.id == currency.id
                )[:1]

                if currency_account:
                    _logger.info(f"Usando cuenta específica para moneda {currency.name}: {currency_account.account_id.name} ({currency_account.account_id.account_type})")

                    # Modificar la línea del asiento que tiene el partner
                    payment_move = payment.move_id
                    partner_lines = payment_move.line_ids.filtered(
                        lambda l: l.partner_id == payment.partner_id and l.account_id.account_type in ['asset_receivable', 'liability_payable']
                    )

                    if partner_lines:
                        partner_lines[0].write({
                            'account_id': currency_account.account_id.id,
                        })
                        _logger.info(f"Línea modificada: {partner_lines[0].account_id.name} ({partner_lines[0].account_id.account_type})")
                    else:
                        _logger.warning("No se encontraron líneas del partner en el asiento del pago")
                else:
                    _logger.warning(f"No se encontró cuenta específica para moneda {currency.name} en el diario del talonario")
            else:
                _logger.warning("El diario del talonario no tiene configuradas cuentas por moneda (account_currency_ids)")

        except Exception as e:
            _logger.error(f"Error modificando cuenta del pago para proveedor: {e}")

    def _modify_payment_account_for_customer(self, payment, currency, payment_journal):
        """
        Modifica el asiento del pago para usar las cuentas correctas del diario del talonario
        para clientes según la moneda específica
        """
        try:
            _logger.info(f"Modificando asiento del pago para cliente usando cuentas del diario del talonario")

            # Buscar la cuenta correcta según la moneda en el diario del talonario
            # El diario del talonario tiene configuradas las cuentas por moneda en account_currency_ids
            if hasattr(payment_journal, 'account_currency_ids'):
                currency_account = payment_journal.account_currency_ids.filtered(
                    lambda c: c.currency_id.id == currency.id
                )[:1]

                if currency_account:
                    _logger.info(f"Usando cuenta específica para moneda {currency.name}: {currency_account.account_id.name} ({currency_account.account_id.account_type})")

                    # Modificar la línea del asiento que tiene el partner
                    payment_move = payment.move_id
                    partner_lines = payment_move.line_ids.filtered(
                        lambda l: l.partner_id == payment.partner_id and l.account_id.account_type in ['asset_receivable', 'liability_payable']
                    )

                    if partner_lines:
                        partner_lines[0].write({
                            'account_id': currency_account.account_id.id,
                        })
                        _logger.info(f"Línea modificada: {partner_lines[0].account_id.name} ({partner_lines[0].account_id.account_type})")
                    else:
                        _logger.warning("No se encontraron líneas del partner en el asiento del pago")
                else:
                    _logger.warning(f"No se encontró cuenta específica para moneda {currency.name} en el diario del talonario")
            else:
                _logger.warning("El diario del talonario no tiene configuradas cuentas por moneda (account_currency_ids)")

        except Exception as e:
            _logger.error(f"Error modificando cuenta del pago para cliente: {e}")

    def _reconcile_supplier_payment_with_invoice(self, payment, invoice):
        """
        Reconcilia un pago de proveedor con su factura correspondiente
        """
        try:
            _logger.info(f"Reconciliando pago {payment.name} con factura {invoice.name}")

            # Buscar las líneas de la factura que coincidan con el pago
            invoice_lines = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                and l.amount_residual != 0
            )

            # Buscar las líneas del pago que coincidan
            payment_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
            )

            _logger.info(f"Líneas de factura encontradas: {len(invoice_lines)}")
            _logger.info(f"Líneas de pago encontradas: {len(payment_lines)}")

            # Reconciliar las líneas compatibles
            if invoice_lines and payment_lines:
                # Buscar líneas compatibles por partner (más flexible)
                for invoice_line in invoice_lines:
                    _logger.info(f"Buscando línea compatible para factura: {invoice_line.account_id.name} - Partner: {invoice_line.partner_id.name}")

                    # Primero intentar por cuenta exacta y partner
                    compatible_payment_line = payment_lines.filtered(
                        lambda l: l.account_id == invoice_line.account_id
                        and l.partner_id == invoice_line.partner_id
                    )

                    # Si no encuentra, intentar solo por partner y tipo de cuenta
                    if not compatible_payment_line:
                        compatible_payment_line = payment_lines.filtered(
                            lambda l: l.account_id.account_type == invoice_line.account_id.account_type
                            and l.partner_id == invoice_line.partner_id
                        )

                    _logger.info(f"Líneas compatibles encontradas: {len(compatible_payment_line)}")

                    if compatible_payment_line:
                        try:
                            # Verificar que las líneas tengan montos compatibles
                            invoice_amount = abs(invoice_line.amount_residual)
                            payment_amount = abs(compatible_payment_line[0].balance)

                            _logger.info(f"Monto factura: {invoice_amount}, Monto pago: {payment_amount}")

                            if invoice_amount > 0 and payment_amount > 0:
                                (invoice_line | compatible_payment_line[0]).reconcile()
                                _logger.info(f"✓ Pago {payment.name} reconciliado con factura {invoice.name}")
                                break
                            else:
                                _logger.warning(f"Montos no compatibles para reconciliación: factura={invoice_amount}, pago={payment_amount}")
                        except Exception as e:
                            _logger.warning(f"No se pudo reconciliar pago {payment.name} con factura {invoice.name}: {e}")
                    else:
                        _logger.warning(f"No se encontraron líneas compatibles para factura {invoice.name}")
            else:
                _logger.warning(f"No hay líneas para reconciliar: factura={len(invoice_lines)}, pago={len(payment_lines)}")

        except Exception as e:
            _logger.error(f"Error reconciliando pago {payment.name} con factura {invoice.name}: {e}")

    def _create_reverse_payment_for_suppliers(self, created_payments):
        """
        Crea un pago contrario para proveedores que reconcilie contra los métodos de pago del agrupador
        """
        try:
            _logger.info(f"Creando pago contrario para proveedores")

            # Calcular el monto total de los pagos creados
            total_amount = sum(created_payments.mapped('amount'))
            currency = created_payments[0].currency_id if created_payments else self.currency_id

            _logger.info(f"Monto total del pago contrario: {total_amount} - Moneda: {currency.name}")

            # Usar el diario intermedio del agrupador para el pago contrario
            intermediate_journal = self.account_journal_aggregator_id.account_journal_id

            # Determinar tipo de pago contrario basado en el talonario
            if self.receiptbook_id.type == 'outbound':
                reverse_payment_type = 'inbound'  # Si pagamos a proveedores, recibimos del banco
                partner_type = 'supplier'
            else:
                reverse_payment_type = 'outbound'  # Si recibimos de proveedores, pagamos al banco
                partner_type = 'supplier'

            # Buscar método de pago apropiado
            if reverse_payment_type == 'inbound':
                method_line = intermediate_journal.inbound_payment_method_line_ids.filtered(
                    lambda m: m.payment_method_id.code == 'manual'
                )[:1] or intermediate_journal.inbound_payment_method_line_ids[:1]
            else:
                method_line = intermediate_journal.outbound_payment_method_line_ids.filtered(
                    lambda m: m.payment_method_id.code == 'manual'
                )[:1] or intermediate_journal.outbound_payment_method_line_ids[:1]

            # Crear pago contrario
            reverse_payment_vals = {
                'payment_type': reverse_payment_type,
                'partner_type': partner_type,
                'partner_id': self.customer_id.id,  # Usar el partner del agrupador
                'amount': total_amount,
                'currency_id': currency.id,
                'journal_id': intermediate_journal.id,
                'date': self.date,
                'ref': f'Pago inverso proveedor - {self.name}',
                'payment_method_line_id': method_line.id if method_line else False,
                'payment_aggregator_id': self.id,
            }

            # Agregar tipo de documento si es necesario
            if hasattr(self.receiptbook_id, 'document_type_id') and self.receiptbook_id.document_type_id:
                reverse_payment_vals['l10n_latam_document_type_id'] = self.receiptbook_id.document_type_id.id
            else:
                # Buscar tipo de documento por defecto
                default_doc_type = self._get_default_document_type(intermediate_journal)
                if default_doc_type:
                    reverse_payment_vals['l10n_latam_document_type_id'] = default_doc_type.id

            reverse_payment = self.env['account.payment'].create(reverse_payment_vals)
            reverse_payment.action_post()

            _logger.info(f"✓ Pago contrario creado: {reverse_payment.name}")
            return reverse_payment

        except Exception as e:
            _logger.error(f"Error creando pago contrario para proveedores: {e}")
            return None

