from odoo import _, api, fields, models, tools
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

check_codes = ["new_third_party_checks","in_third_party_checks", "out_third_party_checks","check_printing"]

class MPPaymentMethodsLine(models.Model):

    _name = 'mps.payment.methods.line'
    _description = 'Model to save the payment methods'

    # importe
    payment_amount = fields.Monetary(
        currency_field="currency_id"
    )
    # Moneda
    currency_id = fields.Many2one(
        'res.currency',
        string='currency'
    )
    payment_aggregator_currency_id = fields.Many2one(
        'res.currency',
        store=False
    )
    # monto del recibo
    amount = fields.Float()
    # fecha
    date = fields.Date(related='mps_payment_aggregator_id.date')
    # memo
    memo = fields.Char()

    account_journal_id = fields.Many2one(
        'account.journal',
        string='Account Journal',
        domain=lambda self: str(self._getAccountJournalDomain())
    )

    have_journal_currency = fields.Boolean(default=True)

    payment_type = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound','Inbound')
    ],
    related='mps_payment_aggregator_id.receiptbook_id.type')
    payment_type_visibility = fields.Boolean(
        default=False,
        store=False
    )
    payment_method_id = fields.Many2one(
        'account.payment.method',
        string='Payment Method',
        related='payment_method_line_id.payment_method_id',
    )
    payment_method_code = fields.Char(related='payment_method_id.code')
    
    available_payment_method_line_ids = fields.Many2many(
        'account.payment.method.line',
        compute='_compute_payment_method_line_fields'
    )
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', 
        string='Payment Method',
        readonly=False, 
        store=True, 
        copy=False,
        compute='_compute_payment_method_line_id',
        help="Manual: Pay or Get paid by any method outside of Odoo.\n"
        "Payment Providers: Each payment provider has its own Payment Method. Request a transaction on/to a card thanks to a payment token saved by the partner when buying or subscribing online.\n"
        "Check: Pay bills by check and print it from Odoo.\n"
        "Batch Deposit: Collect several customer checks at once generating and submitting a batch deposit to your bank. Module account_batch_payment is necessary.\n"
        "SEPA Credit Transfer: Pay in the SEPA zone by submitting a SEPA Credit Transfer file to your bank. Module account_sepa is necessary.\n"
        "SEPA Direct Debit: Get paid in the SEPA zone thanks to a mandate your partner will have granted to you. Module account_sepa is necessary.\n"
    )
    exchange_rate = fields.Float(default=1)
    exchange_rate_visibility = fields.Boolean(
        default=False,
    )

    mps_payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='Payment Aggregator',
    )

    payment_method_domain = fields.Char()

    # Cheques - CAMPOS CORREGIDOS
    is_check = fields.Boolean(default=False)
    check_number = fields.Char()
    check_cash_date = fields.Date()
    
    # CAMPO CORREGIDO: Many2one en lugar de Char
    check_bank_id = fields.Many2one(
        'res.bank',
        string='Check Bank'
    )
    
    # Campo computado para mostrar el nombre del banco
    check_bank = fields.Char(
        string='Bank Name',
        related='check_bank_id.name',
        readonly=True
    )
    
    check_vat = fields.Char()

    # existent_check
    check_id = fields.Many2one(
        comodel_name='account.payment',
        string='Check',
        copy=False,
        check_company=True,
    )
    check_domain = fields.Char()

    # Adenda
    adenda = fields.Char()

    company_id = fields.Many2one(
        'res.company',
        string='company',
        default=lambda self: self.env.company
    )

    # Metodo para asignar el dominio de los metodos de pago
    @api.onchange('account_journal_id')
    def onchange_account_journal_id(self):
        if not self.account_journal_id:
            self.payment_method_domain = "[]"
            self._getVisibilityPaymentType()
            self.payment_aggregator_currency_id = self._getPaymentAggregatorCurrency()
            self.have_journal_currency = False
        else:
            # Calcular métodos de pago disponibles
            self._compute_payment_method_line_fields()
            self.payment_method_domain = "[('id', 'in', %s), ('payment_method_id.code', '!=', 'in_third_party_checks')]" % (self.available_payment_method_line_ids.ids or [])

            if not self.account_journal_id.currency_id:
                self.currency_id = self.env.company.currency_id
                self.have_journal_currency = False
            else:
                self.currency_id = self.account_journal_id.currency_id
                self.have_journal_currency = True

    @api.onchange('currency_id')
    def onchange_currency_id(self):
        if self.currency_id and self.payment_aggregator_currency_id:
            self.exchange_rate_visibility = not self._checkSameCurrency()
            if self.exchange_rate_visibility:
                currency_rate = self._getCurrencyRate()
                self.exchange_rate = currency_rate["inverse_company_rate"] if currency_rate else 1
            self.onchange_payment_amount()

    def _checkSameCurrency(self):
        """Verificar si se está usando la misma moneda"""
        return self.currency_id.id == self.payment_aggregator_currency_id.id

    @api.onchange('payment_amount','exchange_rate','amount')
    def onchange_payment_amount(self):
        """Calcular conversión de monedas CORREGIDA"""
        if self.payment_amount:
            if self._checkSameCurrency() or not self.exchange_rate:
                self.amount = self.payment_amount
            else:
                # Aplicar tasa de cambio
                if self.exchange_rate != 0:
                    self.amount = self.payment_amount * self.exchange_rate
                else:
                    self.amount = self.payment_amount

    @api.onchange('payment_method_id')
    def onchange_payment_method_id(self):
        if self.payment_method_id:
            self.is_check = self.payment_method_id.code in check_codes

    def _getPaymentAggregatorCurrency(self):
        return self.env["res.currency"].search(
            [("id","=",self.env.context.get("currency_id"))],
            limit=1
        )

    def _getVisibilityPaymentType(self):
        receiptbook = self._getReceiptbookContext()
        if receiptbook:
            self.payment_type_visibility = receiptbook.enable_reverse_payment

    def _getPaymentMethodDomain(self):
        return self._generatePaymentMethodDomain()
    
    def _generatePaymentMethodDomain(self):
        if self.account_journal_id:
            payment_methods = False
            receiptbook = self._getReceiptbookContext()
            aggregator_currency = self._getPaymentAggregatorCurrency()

            if aggregator_currency and aggregator_currency.id == self.currency_id.id:
                self.exchange_rate = 1

            if receiptbook:
                if receiptbook.type == "inbound":
                    payment_methods = self.account_journal_id.inbound_payment_method_line_ids
                else:
                    payment_methods = self.account_journal_id.outbound_payment_method_line_ids

                payment_method_ids = payment_methods.mapped("payment_method_id.id")
                return [('payment_method_id.id', 'in', payment_method_ids)] 
        return []
    
    def _getReceiptbookContext(self):
        if self.env.context.get('receiptbook_id'):
            return self.env['mps.receipt.books'].search(
                [("id","=",self.env.context.get('receiptbook_id'))],
                limit=1
            )
        return False
    
    def _get_default_payment_method(self):
        domain = self._getPaymentMethodDomain()
        payment_method = self.env['account.payment.method'].search(domain, limit=1)
        return payment_method.id if payment_method else False
    
    def _getAccountJournalDomain(self):
        return ['|',('type','=','cash'),('type','=','bank'),('intermediate_diary','=',False),('company_id','=', self.env.company.id)]

    def _getCurrencyRate(self):
        """MÉTODO CORREGIDO para obtener tasa de cambio"""
        if self.currency_id.id == self.env.company.currency_id.id:
            currency = self.payment_aggregator_currency_id
        else:
            currency = self.currency_id

        if currency and currency.rate_ids:
            latest_rate = currency.rate_ids.sorted('name', reverse=True)[:1]
            if latest_rate:
                return {
                    'rate': latest_rate.rate,
                    'inverse_company_rate': 1 / latest_rate.rate if latest_rate.rate else 1
                }
        return {'rate': 1, 'inverse_company_rate': 1}

    @api.depends('available_payment_method_line_ids')
    def _compute_payment_method_line_id(self):
        for pay in self:
            available_payment_method_lines = pay.available_payment_method_line_ids

            if pay.payment_method_line_id in available_payment_method_lines:
                pay.payment_method_line_id = pay.payment_method_line_id
            elif available_payment_method_lines:
                pay.payment_method_line_id = available_payment_method_lines[0]._origin
            else:
                pay.payment_method_line_id = False

    @api.depends('payment_type', 'account_journal_id')
    def _compute_payment_method_line_fields(self):
        for pay in self:
            if pay.account_journal_id:
                try:
                    pay.available_payment_method_line_ids = pay.account_journal_id._get_available_payment_method_lines(pay.payment_type)
                    to_exclude = pay._get_payment_method_codes_to_exclude()
                    if to_exclude:
                        pay.available_payment_method_line_ids = pay.available_payment_method_line_ids.filtered(lambda x: x.code not in to_exclude)
                except:
                    pay.available_payment_method_line_ids = self.env['account.payment.method.line']
            else:
                pay.available_payment_method_line_ids = self.env['account.payment.method.line']

    def _get_payment_method_codes_to_exclude(self):
        self.ensure_one()
        return []
    
    @api.onchange('payment_method_id')
    def onchange_payment_method_id_check_domain(self):
        if self.payment_method_id:
            self.check_domain = str([("l10n_latam_check_current_journal_id.inbound_payment_method_line_ids.payment_method_id.code", "in", ["new_third_party_checks", "in_third_party_checks"]), ('state', '=', 'posted')])
