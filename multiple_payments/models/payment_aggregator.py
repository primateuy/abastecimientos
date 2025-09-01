from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class PaymentAggregator(models.Model):

    _name = 'mps.payment.aggregator'
    _description = 'Model to save payment aggregator'

    name = fields.Char(required=True, default="Borrador")
    company_id = fields.Many2one('res.company', string='company')
    currency_id = fields.Many2one('res.currency', string='currency', required=False)
    
    account_journal_aggregator_id = fields.Many2one(
        'account.journal.aggregator',
        string='Intermediate diary',
        required=True,
        domain=lambda self: "[('company_id','=', %s),('currency_id','=',currency_id)]" % self.env.company.id
    )

    account_journals_currency_ids = fields.Many2many(
        'res.currency', 
        compute="_get_account_journals_currency_domain_compute"
    )

    state = fields.Selection([('draft', 'Draft'), ('published','Published')], default="draft")
    receiptbook_id = fields.Many2one("mps.receipt.books", required=True)
    domain_receiptbook_id = fields.Char(default="[('is_public','=',True)]")
    customer_id = fields.Many2one('res.partner', string='customer', required=True)
    adenda = fields.Char(string="Adenda")
    date = fields.Date(required=True)

    # Campos monetarios
    amount = fields.Monetary(currency_field="currency_id", compute="_compute_amount")
    payment_account = fields.Monetary(currency_field="currency_id")
    debt_allocation = fields.Monetary(currency_field="currency_id", compute="_compute_debt_allocation")
    difference = fields.Monetary(currency_field="currency_id", compute="_compute_difference")
    average_rate = fields.Float(compute='_compute_average_rate')

    # Relaciones
    mps_payment_methods_line_ids = fields.One2many('mps.payment.methods.line', 'mps_payment_aggregator_id')
    mps_credits_line_ids = fields.Many2many('account.move.line', string='Cuentas por Pagar/Cobrar')
    account_move_line_payment_agg_ids = fields.One2many('account.move.line.payment.aggregator', 'payment_aggregator_id')

    @api.depends('mps_payment_methods_line_ids.exchange_rate')
    def _compute_average_rate(self):
        for record in self:
            payment_lines = record.mps_payment_methods_line_ids
            if payment_lines:
                record.average_rate = sum(payment_lines.mapped("exchange_rate")) / len(payment_lines)
            else: 
                record.average_rate = 0

    @api.depends('mps_payment_methods_line_ids.amount')
    def _compute_amount(self):
        for record in self:
            record.amount = sum(record.mps_payment_methods_line_ids.mapped("amount"))

    @api.onchange('adenda')
    def onchange_adenda(self):
        if self.adenda and self.mps_payment_methods_line_ids:
            for method in self.mps_payment_methods_line_ids:
                method.adenda = self.adenda
    
    @api.depends('account_journals_currency_ids')
    def _get_account_journals_currency_domain_compute(self):
        for record in self:
            account_journals = record.env["account.journal.aggregator"].search([("company_id","=", self.env.company.id)])
            record.account_journals_currency_ids = account_journals.mapped("currency_id")

    def button_change_state(self):
        """MÉTODO SIMPLIFICADO: Crear un pago por cada método de pago"""
        if self.state == "draft":
            # Validaciones básicas
            if not self.mps_payment_methods_line_ids:
                raise ValidationError(_("Must have at least one payment method"))
            if self.difference != 0:
                raise ValidationError(_("Difference must be 0 to publish"))
            
            try:
                # Crear un pago independiente por cada método de pago
                self._create_individual_payments()
                self.state = "published"
                
            except Exception as e:
                _logger.error(f"Error en button_change_state: {str(e)}")
                raise UserError(str(e))
        else:
            self.state = "draft"

    def _create_individual_payments(self):
        """
        ESTRATEGIA SIMPLE: Un pago por cada método de pago
        Sin lógica compleja de reconciliación automática
        """
        _logger.info("=== CREANDO PAGOS INDIVIDUALES ===")
        
        for payment_method in self.mps_payment_methods_line_ids:
            self._create_single_payment(payment_method)
        
        # Crear pago a cuenta si existe
        if self.payment_account > 0:
            self._create_account_payment()
            
        _logger.info("=== PAGOS INDIVIDUALES COMPLETADOS ===")

    def _create_single_payment(self, payment_method):
        """Crear un solo pago para un método específico"""
        journal = payment_method.account_journal_id
        if not journal:
            raise UserError(f"Payment method must have a journal")
        
        # Determinar método de pago
        if self.receiptbook_id.type == "inbound":
            method_lines = journal.inbound_payment_method_line_ids
            payment_type = 'inbound'
        else:
            method_lines = journal.outbound_payment_method_line_ids  
            payment_type = 'outbound'
        
        # Seleccionar método de pago apropiado
        method_line = method_lines.filtered(lambda m: m.id == payment_method.payment_method_line_id.id)
        if not method_line:
            method_line = method_lines.filtered(lambda m: m.payment_method_id.code == 'manual')[:1]
        if not method_line:
            method_line = method_lines[:1]
            
        if not method_line:
            raise UserError(f"No payment method available for journal {journal.name}")

        # Crear pago
        payment_vals = {
            'payment_type': payment_type,
            'partner_type': self.receiptbook_id.partner_type,
            'partner_id': self.customer_id.id,
            'amount': payment_method.payment_amount,
            'currency_id': payment_method.currency_id.id,
            'date': payment_method.date or self.date,
            'ref': f'{self.name} - {journal.name}',
            'journal_id': journal.id,
            'payment_method_line_id': method_line.id,
            'is_internal_transfer': False,
            'payment_aggregator_id': self.id,
        }
        
        # Campos de cheques
        if payment_method.is_check:
            payment_vals.update({
                'l10n_latam_check_number': payment_method.check_number,
                'l10n_latam_check_payment_date': payment_method.check_cash_date,
                'l10n_latam_check_bank_id': payment_method.check_bank_id.id,
                'l10n_latam_check_issuer_vat': payment_method.check_vat,
                'l10n_latam_check_current_journal_id': journal.id,
            })

        try:
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()
            
            if payment.state != 'posted':
                payment.move_id._post(soft=False)
                payment.write({'state': 'posted'})
            
            # Marcar líneas del asiento
            if payment.move_id:
                payment.move_id.line_ids.write({'payment_aggregator_id': self.id})
            
            _logger.info(f"✓ Pago creado: {payment.name} - ${payment.amount} {payment.currency_id.name}")
            
        except Exception as e:
            _logger.error(f"Error creando pago para {journal.name}: {str(e)}")
            raise UserError(f"Error creating payment for {journal.name}: {str(e)}")

    def _create_account_payment(self):
        """Crear pago a cuenta simple"""
        # Usar primer método como referencia para el diario
        first_method = self.mps_payment_methods_line_ids[0]
        journal = first_method.account_journal_id
        
        # Método de pago manual
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
            'currency_id': self.currency_id.id,
            'date': self.date,
            'ref': f'Payment on Account: {self.name}',
            'journal_id': journal.id,
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
            
            if payment.move_id:
                payment.move_id.line_ids.write({'payment_aggregator_id': self.id})
                
            _logger.info(f"✓ Pago a cuenta creado: ${self.payment_account}")
            
        except Exception as e:
            raise UserError(f"Error creating account payment: {str(e)}")

    # MÉTODOS DE CÁLCULO
    @api.depends('amount', 'payment_account', 'debt_allocation')
    def _compute_difference(self):
        for record in self:
            record.difference = record.amount - (record.payment_account + record.debt_allocation)

    @api.depends('account_move_line_payment_agg_ids.payment_aggregator_total_import')
    def _compute_debt_allocation(self):
        for record in self:
            record.debt_allocation = sum(record.account_move_line_payment_agg_ids.mapped('payment_aggregator_total_import'))

    # MÉTODOS DE FACTURAS
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

    def search_account_move_line(self):
        domain = [
            ('partner_id', '=', self.customer_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']), 
            ('move_id.move_type', 'in', ['out_invoice','in_invoice']),
            ('move_id.state','=','posted')
        ]
        return self.env['account.move.line'].search(domain)
    
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
                    aggregator_ids.append(aggregator_record.id)
        self.account_move_line_payment_agg_ids = [(6, 0, aggregator_ids)]

    # MÉTODOS DE INTERFAZ
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
            'domain': [('payment_aggregator_id', '=', self.id)]
        }
    
    def button_update_accounting_notes(self):
        self.filter_credit_moves()
        return
    
    def button_delete_accounting_notes(self):
        lines_to_remove = self.account_move_line_payment_agg_ids.filtered(
            lambda line: line.payment_aggregator_total_import == 0
        )
        self.write({'account_move_line_payment_agg_ids': [(3, line.id) for line in lines_to_remove]})
        return True

    def button_apply_fifo(self):
        if self.difference > 0 and self.account_move_line_payment_agg_ids:
            sorted_moves = self.account_move_line_payment_agg_ids.sorted(
                key=lambda r: r.date or fields.Date.today()
            )
            
            remaining_difference = self.difference
            for move in sorted_moves:
                if remaining_difference <= 0:
                    break
                if move.payment_aggregator_total_import == 0:
                    total_import = abs(move.credit) + abs(move.debit)
                    if total_import <= remaining_difference:
                        move.payment_aggregator_total_import = total_import
                        remaining_difference -= total_import

    def button_assign_all(self):
        remaining_difference = self.difference
        for record in self.account_move_line_payment_agg_ids:
            if remaining_difference <= 0:
                break
            if record.payment_aggregator_total_import == 0:
                total_import = record.credit + record.debit
                if total_import <= remaining_difference:
                    record.payment_aggregator_total_import = total_import
                    remaining_difference -= total_import

    # MÉTODOS DEL SISTEMA
    @api.model
    def create(self, values):
        values['company_id'] = self.env.company.id
        result = super().create(values)
        result.name = self.env['ir.sequence'].next_by_code('aggregator.sequence')
        return result
    
    @api.onchange('receiptbook_id')
    def _validate_recieptbook(self):
        if self.receiptbook_id.partner_type:
            if str(self.receiptbook_id.partner_type) not in self.domain_receiptbook_id:
                raise ValidationError(
                    _('You cannot set a %s receipt type in this payment aggregator') % 
                    self.receiptbook_id.partner_type.capitalize()
                )