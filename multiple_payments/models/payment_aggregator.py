from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class PaymentAggregator(models.Model):
    _name = 'mps.payment.aggregator'
    _description = 'Model to save payment aggregator'

    # Campos básicos
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

    # MÉTODO PRINCIPAL COMPLETAMENTE REESCRITO
    def button_change_state(self):
        if self.state == "draft":
            # Validaciones
            if not self.mps_payment_methods_line_ids:
                raise ValidationError(_("To make payments you must load the payments in the payment lines."))
            if self.difference != 0:
                raise ValidationError(_("Difference must be 0 to publish a payments aggregator."))
            
            try:
                # Nuevo flujo simplificado
                self._create_invoice_payments()
                self._create_payment_on_account()
                self._create_internal_transfers()
                self.state = "published"
            except Exception as e:
                _logger.error(f"Error processing payment aggregator: {e}")
                raise UserError(str(e))

    def _create_invoice_payments(self):
        """Crear pagos por facturas/deudas pendientes"""
        if not self.account_move_line_payment_agg_ids:
            return
        
        # Eliminar líneas con importe 0
        self._delete_accounting_notes()
        
        intermediate_journal = self.account_journal_aggregator_id.account_journal_id
        
        for credit_line in self.account_move_line_payment_agg_ids:
            if credit_line.payment_aggregator_total_import <= 0:
                continue
                
            payment_vals = {
                'partner_id': self.customer_id.id,
                'date': self.date,  # FECHA CORREGIDA
                'amount': credit_line.payment_aggregator_total_import,
                'payment_type': self.receiptbook_id.type,
                'partner_type': self.receiptbook_id.partner_type,
                'journal_id': intermediate_journal.id,
                'currency_id': self.currency_id.id,
                'ref': f"{self.adenda or ''} - {credit_line.move_id.name}".strip(' -'),
                'payment_aggregator_id': self.id,
                'transaction_type': 'customer_payment' if self.receiptbook_id.partner_type == 'customer' else 'vendor_payment'
            }
            
            # Obtener método de pago por defecto
            payment_method_line = self._get_default_payment_method_line(intermediate_journal, self.receiptbook_id.type)
            if payment_method_line:
                payment_vals.update({
                    'payment_method_line_id': payment_method_line.id,
                    'payment_method_id': payment_method_line.payment_method_id.id
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
            'date': self.date,  # FECHA CORREGIDA
            'amount': self.payment_account,
            'payment_type': self.receiptbook_id.type,
            'partner_type': self.receiptbook_id.partner_type,
            'journal_id': intermediate_journal.id,
            'currency_id': self.currency_id.id,
            'ref': f"{self.adenda or ''} - Pago a cuenta".strip(' -'),
            'payment_aggregator_id': self.id,
            'transaction_type': 'customer_payment' if self.receiptbook_id.partner_type == 'customer' else 'vendor_payment'
        }
        
        payment_method_line = self._get_default_payment_method_line(intermediate_journal, self.receiptbook_id.type)
        if payment_method_line:
            payment_vals.update({
                'payment_method_line_id': payment_method_line.id,
                'payment_method_id': payment_method_line.payment_method_id.id
            })
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

    def _create_internal_transfers(self):
        """Crear transferencias internas SIMPLIFICADAS"""
        intermediate_journal = self.account_journal_aggregator_id.account_journal_id
        
        for method_line in self.mps_payment_methods_line_ids:
            self._create_single_internal_transfer(method_line, intermediate_journal)

    def _create_single_internal_transfer(self, method_line, intermediate_journal):
        """Crear una transferencia interna individual CORREGIDA"""
        method_journal = method_line.account_journal_id
        
        # Importes correctos
        amount_method_currency = method_line.payment_amount
        amount_aggregator_currency = method_line.amount
        
        # Sentido de transferencia
        if self.receiptbook_id.type == 'inbound':  # Recibir dinero
            origin_journal = method_journal
            destination_journal = intermediate_journal
            origin_payment_type = 'outbound'
            destination_payment_type = 'inbound'
            origin_amount = amount_method_currency
            destination_amount = amount_aggregator_currency
        else:  # Enviar dinero
            origin_journal = intermediate_journal
            destination_journal = method_journal
            origin_payment_type = 'outbound'
            destination_payment_type = 'inbound'
            origin_amount = amount_aggregator_currency
            destination_amount = amount_method_currency

        # Crear pago origen
        origin_payment_vals = {
            'partner_id': self.customer_id.id,  # PARTNER CORREGIDO
            'date': self.date,  # FECHA CORREGIDA
            'amount': origin_amount,
            'payment_type': origin_payment_type,
            'partner_type': 'supplier',
            'journal_id': origin_journal.id,
            'currency_id': origin_journal.currency_id.id or self.env.company.currency_id.id,
            'is_internal_transfer': True,
            'ref': f"{method_line.adenda or self.adenda or ''} - Transferencia".strip(' -'),
            'payment_aggregator_id': self.id,
            'transaction_type': 'internal_transfer'
        }
        
        # Campos de cheque CORREGIDOS
        if method_line.is_check:
            check_fields = self._get_check_fields(method_line)
            origin_payment_vals.update(check_fields)
        
        origin_method_line = self._get_default_payment_method_line(origin_journal, origin_payment_type)
        if origin_method_line:
            origin_payment_vals.update({
                'payment_method_line_id': origin_method_line.id,
                'payment_method_id': origin_method_line.payment_method_id.id
            })

        origin_payment = self.env['account.payment'].create(origin_payment_vals)

        # Crear pago destino
        destination_payment_vals = {
            'partner_id': self.customer_id.id,  # PARTNER CORREGIDO
            'date': self.date,  # FECHA CORREGIDA
            'amount': destination_amount,
            'payment_type': destination_payment_type,
            'partner_type': 'customer',
            'journal_id': destination_journal.id,
            'currency_id': destination_journal.currency_id.id or self.env.company.currency_id.id,
            'is_internal_transfer': True,
            'ref': f"{method_line.adenda or self.adenda or ''} - Transferencia".strip(' -'),
            'payment_aggregator_id': self.id,
            'transaction_type': 'internal_transfer'
        }

        destination_method_line = self._get_default_payment_method_line(destination_journal, destination_payment_type)
        if destination_method_line:
            destination_payment_vals.update({
                'payment_method_line_id': destination_method_line.id,
                'payment_method_id': destination_method_line.payment_method_id.id
            })

        destination_payment = self.env['account.payment'].create(destination_payment_vals)

        # Vincular transferencias
        origin_payment.write({
            'paired_internal_transfer_payment_id': destination_payment.id,
            'destination_journal_id': destination_journal.id
        })
        destination_payment.write({
            'paired_internal_transfer_payment_id': origin_payment.id
        })

        # Publicar ambos pagos
        origin_payment.action_post()
        destination_payment.action_post()

    def _get_check_fields(self, method_line):
        """Obtener campos de cheque CORREGIDOS"""
        check_fields = {}
        if method_line.check_number:
            check_fields['l10n_latam_check_number'] = method_line.check_number
        if method_line.check_cash_date:
            check_fields['l10n_latam_check_payment_date'] = method_line.check_cash_date
        if method_line.check_bank_id:  # CORREGIDO: usar check_bank_id
            check_fields['l10n_latam_check_bank_id'] = method_line.check_bank_id.id
        if method_line.check_vat:
            check_fields['l10n_latam_check_issuer_vat'] = method_line.check_vat
        if method_line.account_journal_id:
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

    # Mantener métodos existentes para botones y otros
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

    # Mantener otros métodos existentes
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
                # Buscar un diario disponible para usar como intermedio
                available_journal = self.env['account.journal'].search([
                    ('type', 'in', ['bank', 'cash']),
                    ('company_id', '=', self.env.company.id),
                    '|', ('currency_id', '=', self.currency_id.id), ('currency_id', '=', False),
                    ('intermediate_diary', '=', False)
                ], limit=1)
                
                if available_journal:
                    # Crear el diario intermedio automáticamente
                    intermediate_diary = self.env["account.journal.aggregator"].create({
                        'account_journal_id': available_journal.id,
                        'company_id': self.env.company.id,
                        'currency_id': self.currency_id.id
                    })
                    # Marcar el diario como intermedio
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
        # Asegurar que company_id siempre esté presente
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
                        