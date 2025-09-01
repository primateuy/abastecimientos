from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class PaymentAggregator(models.Model):
    _name = 'mps.payment.aggregator'
    _description = 'Model to save payment aggregator'

    # Campos básicos (mantener los existentes)
    name = fields.Char(required=True, default="Borrador")
    company_id = fields.Many2one(
        'res.company', 
        string='company',
        default=lambda self: self.env.company,
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency', 
        string='currency', 
        domain="[('active','=',True)]", 
        required=True
    )
    account_journal_aggregator_id = fields.Many2one('account.journal.aggregator', string='Intermediate diary', required=True, domain=lambda self: "[('company_id','=', %s),('currency_id','=',currency_id)]" % self.env.company.id)
    account_journals_currency_ids = fields.Many2many('res.currency', domain=lambda self: str(self._get_account_journals_currency_domain()), compute="_get_account_journals_currency_domain_compute")
    state = fields.Selection([('draft', 'Draft'), ('published','Published')], default="draft")
    receiptbook_id = fields.Many2one("mps.receipt.books", required=True)
    domain_receiptbook_id = fields.Char(default="[('is_public','=',True)]")
    customer_id = fields.Many2one('res.partner', string='customer', required=True)
    adenda = fields.Char(string="Adenda")
    date = fields.Date(required=True)
    amount = fields.Monetary(currency_field="currency_id", compute="_compute_amount")
    payment_account = fields.Monetary(currency_field="currency_id")
    debt_allocation = fields.Monetary(currency_field="currency_id", compute="_compute_debt_allocation")
    difference = fields.Monetary(currency_field="currency_id", compute="_compute_difference")
    mps_payment_methods_line_ids = fields.One2many('mps.payment.methods.line', 'mps_payment_aggregator_id')
    mps_credits_line_ids = fields.Many2many('account.move.line', string='Cuentas por Pagar/Cobrar')
    average_rate = fields.Float(compute='_compute_average_rate')
    account_move_line_payment_agg_ids = fields.One2many('account.move.line.payment.aggregator', 'payment_aggregator_id')

    # Métodos compute existentes
    @api.depends('average_rate')
    def _compute_average_rate(self):
        payment_lines = self.mps_payment_methods_line_ids
        if len(payment_lines) > 0:
            self.average_rate = sum(payment_lines.mapped("exchange_rate")) / len(payment_lines)
        else: 
            self.average_rate = 0

    @api.depends('amount')
    def _compute_amount(self):
        for record in self:
            record.amount = sum(self.mps_payment_methods_line_ids.mapped("amount"))

    @api.onchange('adenda')
    def onchange_adenda(self):
        if self.adenda and len(self.mps_payment_methods_line_ids) > 0:
            for method in self.mps_payment_methods_line_ids:
                method.adenda = self.adenda

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

    # MÉTODO PRINCIPAL CORREGIDO PARA ODOO 17
    def button_change_state(self):
        if self.state == "draft":
            # Validaciones
            if not self.mps_payment_methods_line_ids:
                raise ValidationError(_("To make payments you must load the payments in the payment lines."))
            if self.difference != 0:
                raise ValidationError(_("Difference must be 0 to publish a payments aggregator."))
            
            try:
                # Verificar que el campo is_internal_transfer existe
                if not hasattr(self.env['account.payment']._fields, 'is_internal_transfer'):
                    _logger.warning("Field 'is_internal_transfer' not found, using alternative approach")
                    self._create_payments_without_internal_transfer()
                else:
                    # Flujo original pero con validaciones adicionales
                    self._create_invoice_payments()
                    self._create_payment_on_account()
                    self._create_internal_transfers_safe()
                
                self.state = "published"
            except Exception as e:
                _logger.error(f"Error processing payment aggregator: {e}")
                raise UserError(str(e))

    def _create_payments_without_internal_transfer(self):
        """Crear pagos sin usar is_internal_transfer (para casos donde no existe el campo)"""
        self._create_invoice_payments()
        self._create_payment_on_account()
        
        # En lugar de transferencias internas, crear pagos separados
        intermediate_journal = self.account_journal_aggregator_id.account_journal_id
        
        for method_line in self.mps_payment_methods_line_ids:
            # Crear pago de salida desde el método
            self._create_single_payment(
                journal=method_line.account_journal_id,
                amount=method_line.payment_amount,
                payment_type='outbound' if self.receiptbook_id.type == 'inbound' else 'inbound',
                partner_type='supplier',
                ref=f"{method_line.adenda or self.adenda or ''} - Movimiento método".strip(' -'),
                method_line=method_line
            )
            
            # Crear pago de entrada al intermedio
            self._create_single_payment(
                journal=intermediate_journal,
                amount=method_line.amount,
                payment_type='inbound' if self.receiptbook_id.type == 'inbound' else 'outbound',
                partner_type='customer',
                ref=f"{method_line.adenda or self.adenda or ''} - Movimiento intermedio".strip(' -'),
                method_line=None
            )

    def _create_single_payment(self, journal, amount, payment_type, partner_type, ref, method_line=None):
        """Crear un pago individual"""
        payment_vals = {
            'partner_id': self.customer_id.id,
            'date': self.date,
            'amount': amount,
            'payment_type': payment_type,
            'partner_type': partner_type,
            'journal_id': journal.id,
            'currency_id': journal.currency_id.id or self.env.company.currency_id.id,
            'ref': ref,
            'payment_aggregator_id': self.id,
        }
        
        # Campos de cheque si aplica
        if method_line and method_line.is_check:
            check_fields = self._get_check_fields(method_line)
            payment_vals.update(check_fields)
        
        # Método de pago
        payment_method_line = self._get_default_payment_method_line(journal, payment_type)
        if payment_method_line:
            payment_vals.update({
                'payment_method_line_id': payment_method_line.id,
            })
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        return payment

    def _create_invoice_payments(self):
        """Crear pagos por facturas/deudas pendientes"""
        if not self.account_move_line_payment_agg_ids:
            return
        
        self._delete_accounting_notes()
        
        intermediate_journal = self.account_journal_aggregator_id.account_journal_id
        
        for credit_line in self.account_move_line_payment_agg_ids:
            if credit_line.payment_aggregator_total_import <= 0:
                continue
                
            payment_vals = {
                'partner_id': self.customer_id.id,
                'date': self.date,
                'amount': credit_line.payment_aggregator_total_import,
                'payment_type': self.receiptbook_id.type,
                'partner_type': self.receiptbook_id.partner_type,
                'journal_id': intermediate_journal.id,
                'currency_id': self.currency_id.id,
                'ref': f"{self.adenda or ''} - {credit_line.move_id.name}".strip(' -'),
                'payment_aggregator_id': self.id,
            }
            
            # Método de pago
            payment_method_line = self._get_default_payment_method_line(intermediate_journal, self.receiptbook_id.type)
            if payment_method_line:
                payment_vals.update({
                    'payment_method_line_id': payment_method_line.id,
                })
            
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()
            
            # Reconciliar con la factura
            self._reconcile_payment_with_invoice(payment, credit_line)

    def _create_payment_on_account(self):
        """Crear pago a cuenta si existe"""
        if self.payment_account <= 0:
            return
            
        intermediate_journal = self.account_journal_aggregator_id.account_journal_id
        
        payment_vals = {
            'partner_id': self.customer_id.id,
            'date': self.date,
            'amount': self.payment_account,
            'payment_type': self.receiptbook_id.type,
            'partner_type': self.receiptbook_id.partner_type,
            'journal_id': intermediate_journal.id,
            'currency_id': self.currency_id.id,
            'ref': f"{self.adenda or ''} - Pago a cuenta".strip(' -'),
            'payment_aggregator_id': self.id,
        }
        
        payment_method_line = self._get_default_payment_method_line(intermediate_journal, self.receiptbook_id.type)
        if payment_method_line:
            payment_vals.update({
                'payment_method_line_id': payment_method_line.id,
            })
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

    def _create_internal_transfers_safe(self):
        """Crear transferencias internas con validación de campos"""
        intermediate_journal = self.account_journal_aggregator_id.account_journal_id
        
        for method_line in self.mps_payment_methods_line_ids:
            try:
                self._create_single_internal_transfer_safe(method_line, intermediate_journal)
            except Exception as e:
                _logger.error(f"Error creating internal transfer: {e}")
                # Fallback a crear pagos separados
                self._create_separate_payments_fallback(method_line, intermediate_journal)

    def _create_single_internal_transfer_safe(self, method_line, intermediate_journal):
        """Crear una transferencia interna individual con validaciones"""
        method_journal = method_line.account_journal_id
        
        # Importes
        amount_method_currency = method_line.payment_amount
        amount_aggregator_currency = method_line.amount
        
        # Direcciones
        if self.receiptbook_id.type == 'inbound':
            origin_journal = method_journal
            destination_journal = intermediate_journal
            origin_payment_type = 'outbound'
            destination_payment_type = 'inbound'
            origin_amount = amount_method_currency
            destination_amount = amount_aggregator_currency
        else:
            origin_journal = intermediate_journal
            destination_journal = method_journal
            origin_payment_type = 'outbound'
            destination_payment_type = 'inbound'
            origin_amount = amount_aggregator_currency
            destination_amount = amount_method_currency

        # Crear pago origen con validaciones
        origin_payment_vals = self._get_transfer_payment_vals(
            origin_journal, origin_amount, origin_payment_type, 'supplier', method_line, "Transferencia origen"
        )
        
        origin_payment = self.env['account.payment'].create(origin_payment_vals)

        # Crear pago destino
        destination_payment_vals = self._get_transfer_payment_vals(
            destination_journal, destination_amount, destination_payment_type, 'customer', None, "Transferencia destino"
        )

        destination_payment = self.env['account.payment'].create(destination_payment_vals)

        # Verificar si existen los campos antes de usarlos
        if hasattr(origin_payment, 'is_internal_transfer'):
            origin_payment.is_internal_transfer = True
            destination_payment.is_internal_transfer = True
        
        if hasattr(origin_payment, 'paired_internal_transfer_payment_id'):
            origin_payment.paired_internal_transfer_payment_id = destination_payment.id
            destination_payment.paired_internal_transfer_payment_id = origin_payment.id
        
        if hasattr(origin_payment, 'destination_journal_id'):
            origin_payment.destination_journal_id = destination_journal.id

        # Publicar pagos
        origin_payment.action_post()
        destination_payment.action_post()

    def _get_transfer_payment_vals(self, journal, amount, payment_type, partner_type, method_line, ref_suffix):
        """Obtener valores para crear pago de transferencia"""
        payment_vals = {
            'partner_id': self.customer_id.id,
            'date': self.date,
            'amount': amount,
            'payment_type': payment_type,
            'partner_type': partner_type,
            'journal_id': journal.id,
            'currency_id': journal.currency_id.id or self.env.company.currency_id.id,
            'ref': f"{method_line.adenda or self.adenda or ''} - {ref_suffix}".strip(' -'),
            'payment_aggregator_id': self.id,
        }
        
        # Campos de cheque
        if method_line and method_line.is_check:
            check_fields = self._get_check_fields(method_line)
            payment_vals.update(check_fields)
        
        # Método de pago
        payment_method_line = self._get_default_payment_method_line(journal, payment_type)
        if payment_method_line:
            payment_vals.update({
                'payment_method_line_id': payment_method_line.id,
            })
        
        return payment_vals

    def _create_separate_payments_fallback(self, method_line, intermediate_journal):
        """Fallback: crear pagos separados cuando falla la transferencia interna"""
        _logger.info(f"Using fallback method for payment line {method_line.id}")
        
        # Pago desde método
        self._create_single_payment(
            journal=method_line.account_journal_id,
            amount=method_line.payment_amount,
            payment_type='outbound' if self.receiptbook_id.type == 'inbound' else 'inbound',
            partner_type='supplier',
            ref=f"{method_line.adenda or self.adenda or ''} - Fallback método".strip(' -'),
            method_line=method_line
        )
        
        # Pago hacia intermedio
        self._create_single_payment(
            journal=intermediate_journal,
            amount=method_line.amount,
            payment_type='inbound' if self.receiptbook_id.type == 'inbound' else 'outbound',
            partner_type='customer',
            ref=f"{method_line.adenda or self.adenda or ''} - Fallback intermedio".strip(' -'),
            method_line=None
        )

    def _get_check_fields(self, method_line):
        """Obtener campos de cheque con validaciones"""
        check_fields = {}
        
        # Verificar que existan los campos antes de usarlos
        payment_model = self.env['account.payment']
        
        if 'l10n_latam_check_number' in payment_model._fields and method_line.check_number:
            check_fields['l10n_latam_check_number'] = method_line.check_number
        
        if 'l10n_latam_check_payment_date' in payment_model._fields and method_line.check_cash_date:
            check_fields['l10n_latam_check_payment_date'] = method_line.check_cash_date
        
        if 'l10n_latam_check_bank_id' in payment_model._fields and method_line.check_bank_id:
            check_fields['l10n_latam_check_bank_id'] = method_line.check_bank_id.id
        
        if 'l10n_latam_check_issuer_vat' in payment_model._fields and method_line.check_vat:
            check_fields['l10n_latam_check_issuer_vat'] = method_line.check_vat
        
        if 'l10n_latam_check_current_journal_id' in payment_model._fields and method_line.account_journal_id:
            check_fields['l10n_latam_check_current_journal_id'] = method_line.account_journal_id.id
        
        return check_fields

    def _get_default_payment_method_line(self, journal, payment_type):
        """Obtener línea de método de pago por defecto"""
        if payment_type == 'inbound':
            method_lines = journal.inbound_payment_method_line_ids
            default_method_ref = 'account.account_payment_method_manual_in'
        else:
            method_lines = journal.outbound_payment_method_line_ids
            default_method_ref = 'account.account_payment_method_manual_out'
        
        default_method = self.env.ref(default_method_ref, False)
        if default_method:
            method_line = method_lines.filtered(lambda x: x.payment_method_id.id == default_method.id)
            if method_line:
                return method_line[0]
        
        return method_lines[0] if method_lines else False

    def _reconcile_payment_with_invoice(self, payment, credit_line):
        """Reconciliar pago con factura"""
        try:
            payment_lines = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
            )
            
            invoice_lines = credit_line.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
            )
            
            if payment_lines and invoice_lines:
                (payment_lines + invoice_lines).reconcile()
                credit_line.move_id._compute_payment_state()
                
        except Exception as e:
            _logger.warning(f"Error reconciling payment {payment.id}: {e}")

    def _delete_accounting_notes(self):
        """Eliminar líneas con importe 0"""
        lines_to_remove = self.account_move_line_payment_agg_ids.filtered(
            lambda line: line.payment_aggregator_total_import == 0
        )
        self.write({'account_move_line_payment_agg_ids': [(3, line.id) for line in lines_to_remove]})

    # MANTENER TODOS LOS MÉTODOS EXISTENTES
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
        view_id = self.env.ref('multiple_payments.view_account_payment_tree_grouped_simple', False)
        return {
            'name': 'Pagos Agrupados',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'context': {'group_by': ['transaction_type']},
            'domain': [('payment_aggregator_id', '=', self.id)]
        }
    
    def button_update_accounting_notes(self):
        self.filter_credit_moves()
    
    def button_delete_accounting_notes(self):
        self._delete_accounting_notes()
    
    def button_apply_fifo(self):
        if self.difference > 0 and self.account_move_line_payment_agg_ids:
            sorted_moves = self.account_move_line_payment_agg_ids.sorted(key=lambda r: r.date or fields.Date.today())
            remaining_difference = self.difference
            
            for move in sorted_moves:
                if move.payment_aggregator_total_import == 0:
                    total_import = abs(move.credit) + abs(move.debit)
                    if total_import <= 0:
                        continue
                    if remaining_difference >= total_import:
                        move.payment_aggregator_total_import = total_import
                        remaining_difference -= total_import
                    else:
                        break

    def button_assign_all(self):
        for record in self.account_move_line_payment_agg_ids:
            if record.payment_aggregator_total_import == 0:
                total_import = record.credit + record.debit
                if (self.difference - total_import) >= 0:
                    record.payment_aggregator_total_import = total_import

    # MÉTODOS EXISTENTES (mantener sin cambios)
    @api.depends('account_journals_currency_ids')
    def _get_account_journals_currency_domain_compute(self):
        for record in self:
            record.account_journals_currency_ids = self.env["res.currency"].search(record._get_account_journals_currency_domain()).ids

    def _get_account_journals_currency_domain(self):
        for record in self:
            account_journals = record.env["account.journal.aggregator"].search([("company_id","=", self.env.company.id)])
            return [('id','in', account_journals.mapped("currency_id.id"))]

    @api.onchange('customer_id', 'currency_id')
    def filter_credit_moves(self):
        if self.customer_id and self.currency_id:
            self.mps_credits_line_ids = self.search_account_move_line()
            self.set_account_move_line(self.mps_credits_line_ids)
            
            # Buscar o crear diario intermedio
            intermediate_diary = self.env["account.journal.aggregator"].search([
                ('company_id','=',self.env.company.id),
                ('currency_id','=',self.currency_id.id)
            ], limit=1)
            
            if not intermediate_diary:
                available_journal = self.env['account.journal'].search([
                    ('type', 'in', ['bank', 'cash']),
                    ('company_id', '=', self.env.company.id),
                    '|', ('currency_id', '=', self.currency_id.id), ('currency_id', '=', False),
                    ('intermediate_diary', '=', False)
                ], limit=1)
                
                if available_journal:
                    intermediate_diary = self.env["account.journal.aggregator"].create({
                        'account_journal_id': available_journal.id,
                        'company_id': self.env.company.id,
                        'currency_id': self.currency_id.id
                    })
                    available_journal.intermediate_diary = True
            
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

    @api.model
    def create(self, values):
        if not values.get('company_id'):
            values['company_id'] = self.env.company.id
        result = super().create(values)
        result.name = self.env['ir.sequence'].next_by_code('aggregator.sequence')
        return result
    
    @api.onchange('receiptbook_id')
    def _validate_recieptbook(self):
        if self.receiptbook_id.partner_type:
            if str(self.receiptbook_id.partner_type) not in self.domain_receiptbook_id:
                raise ValidationError(_(f'You cannot set a {self.receiptbook_id.partner_type.capitalize()} reciept type in this payment aggregator'))
