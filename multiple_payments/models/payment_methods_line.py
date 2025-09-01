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
    # payment_method_line_id = fields.Many2one(
    #     "account.payment.method.line",
    #     string="Payment Method",
    #     domain=lambda self: str(self._getPaymentMethodDomain()),
    #     default=lambda self: self._get_default_payment_method()
    # )
    available_payment_method_line_ids = fields.Many2many(
        'account.payment.method.line',
        compute='_compute_payment_method_line_fields'
    )
    payment_method_line_id = fields.Many2one('account.payment.method.line', string='Payment Method',
        readonly=False, store=True, copy=False,
        compute='_compute_payment_method_line_id',
        domain=lambda self: "[('id', 'in', %s)]" % self.available_payment_method_line_ids,
        help="Manual: Pay or Get paid by any method outside of Odoo.\n"
        "Payment Providers: Each payment provider has its own Payment Method. Request a transaction on/to a card thanks to a payment token saved by the partner when buying or subscribing online.\n"
        "Check: Pay bills by check and print it from Odoo.\n"
        "Batch Deposit: Collect several customer checks at once generating and submitting a batch deposit to your bank. Module account_batch_payment is necessary.\n"
        "SEPA Credit Transfer: Pay in the SEPA zone by submitting a SEPA Credit Transfer file to your bank. Module account_sepa is necessary.\n"
        "SEPA Direct Debit: Get paid in the SEPA zone thanks to a mandate your partner will have granted to you. Module account_sepa is necessary.\n")
    exchange_rate = fields.Float(default=1)
    exchange_rate_visibility = fields.Boolean(
        default=False,
    )

    mps_payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='Payment Aggregator',
    )

    payment_method_domain = fields.Char()

    # Cheques
    # Visibilidad
    is_check = fields.Boolean(
        default=False
    )

    # Numero
    check_number = fields.Char()

    # Fecha
    check_cash_date = fields.Date()

    # Banco
    check_bank_id = fields.Many2one(
        'res.bank'
    )

    # vat
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
            # Generamos el domain para el metodo de pago
            # self.payment_method_domain = self._generatePaymentMethodDomain()
            self.payment_method_domain = "[('id', 'in', %s), ('payment_method_id.code', '!=', 'in_third_party_checks')]" % self.available_payment_method_line_ids.ids

            # Invocamos el metodo para controlar la visibilidad del tipo de pago
            self._getVisibilityPaymentType()

            # Asignamos la moneda del agrupador de pago
            self.payment_aggregator_currency_id = self._getPaymentAggregatorCurrency()

            self.have_journal_currency = False
        else:
            # Establecemos el domain
            # self.payment_method_domain = str(self._getPaymentMethodDomain())
            self.payment_method_domain = "[('id', 'in', %s), ('payment_method_id.code', '!=', 'in_third_party_checks')]" % self.available_payment_method_line_ids.ids

            if not self.account_journal_id.currency_id:
                self.currency_id = self.env.company.currency_id
                self.have_journal_currency = False

            if self.account_journal_id.currency_id:
                self.currency_id = self.account_journal_id.currency_id
                self.have_journal_currency = True

    @api.onchange('currency_id')
    def onchange_currency_id(self):
        if self.currency_id:
            if self.payment_aggregator_currency_id:
                self.exchange_rate_visibility = self._checkSameCurrency() == False
                if self.exchange_rate_visibility:
                    # Obtenemos tasa
                    currency_rate = self._getCurrencyRate()

                    # _logger.info("===========")
                    # _logger.info(currency_rate)
                    # _logger.info(currency_rate["inverse_company_rate"])
                    # Asignamos
                    if currency_rate == False:
                        self.exchange_rate = 1
                    else:
                        self.exchange_rate = currency_rate["inverse_company_rate"]
            
            self.onchange_payment_amount()

    # Metodo para verificar si se esta usando la misma moneda en el agrupador de pago
    def _checkSameCurrency(self):
        return self.currency_id.id == self.payment_aggregator_currency_id.id

    # Onchange para calcular el precio de la tasa
    @api.onchange('payment_amount','exchange_rate','amount')
    def onchange_payment_amount(self):
        if self.payment_amount and self.exchange_rate and self._checkSameCurrency() == False:
            if  self.payment_aggregator_currency_id.rate > self.currency_id.rate:
                self.amount = self.payment_amount * self.exchange_rate
            else:
                self.amount = self.payment_amount / self.exchange_rate
        elif (self.payment_amount and not self.exchange_rate) or (self.payment_amount and self._checkSameCurrency() == True):
            self.amount = self.payment_amount

    # Onchange para detectar si el metodo de pago es cheques
    @api.onchange('payment_method_id')
    def onchange_payment_method_id(self):
        if self.payment_method_id:
            self.is_check = self.payment_method_id.code in check_codes
            # if self.is_check:
            #     self.check_bank = self.account_journal_id.bank_id.name
    
    # Metodo para obtener la moneda del agrupador pago
    def _getPaymentAggregatorCurrency(self):
        return self.env["res.currency"].search(
            [("id","=",self.env.context.get("currency_id"))],
            limit=1
        )
    # Metodo con el procedimiento de darle valor al campo payment_type_visibility
    # para saber si se debe mostrar el tipo de pago
    def _getVisibilityPaymentType(self):
        receiptbook = self._getReceiptbookContext()
        if receiptbook:
            self.payment_type_visibility = receiptbook.enable_reverse_payment

    # Domain para obtener los metodos de pago segun una condicion previa
    def _getPaymentMethodDomain(self):
        return self._generatePaymentMethodDomain()
    
    # Metodo para generar el domain del metodo de pago
    def _generatePaymentMethodDomain(self):
        if self.account_journal_id:
            payment_methods = False
            # Buscamos el talonario
            receiptbook = self._getReceiptbookContext()
            # Validamos la moneda
            aggregator_currency = self._getPaymentAggregatorCurrency()

            # si es la misma moneda, la tasa de cambio debe ser 1
            if aggregator_currency.id == self.currency_id.id:
                self.exchange_rate = 1

            if receiptbook:
                # Validamos su tipo para asignar los metodos de pago entrantes o salientes
                if receiptbook.type == "inbound":
                    payment_methods = self.account_journal_id.inbound_payment_method_line_ids
                else:
                    payment_methods = self.account_journal_id.outbound_payment_method_line_ids

                # Recorremos la lista de metodos de pago y obtenemos una lista de ids
                payment_method_ids = payment_methods.mapped("payment_method_id.id")

                # retornamos el domain
                return [('payment_method_id.id', 'in', payment_method_ids)] 
        return []
    
    # Metodo para buscar el talonario por el contexto
    def _getReceiptbookContext(self):
        # Si existe algun talonario en el contexto
        if self.env.context.get('receiptbook_id'):
            # Buscamos en el modelo de talonarios
            return self.env['mps.receipt.books'].search(
                [("id","=",self.env.context.get('receiptbook_id'))],
                limit=1
            )
        return False
    
    def _get_default_payment_method(self):
        # Obtenemos el dominio generado por _getPaymentMethodDomain
        domain = self._getPaymentMethodDomain()
        # Buscamos el primer método de pago que cumpla con el dominio
        payment_method = self.env['account.payment.method'].search(domain, limit=1)
        
        return payment_method.id if payment_method else False
    
    # Metodo para obtener el domain para los diarios
    def _getAccountJournalDomain(self):
        return ['|',('type','=','cash'),('type','=','bank'),('intermediate_diary','=',False),('company_id','=', self.env.company.id)]

    # Obtenemos la tasa mas actual
    def _getCurrencyRate(self):
        # Validamos de donde obtener la moneda
        if self.currency_id.id == self.env.company.currency_id.id:
            currency = self.currency_id
        elif self.account_journal_id.currency_id.id == self.env.company.currency_id.id:
            currency = self.env.company.currency_id.id
        elif self.account_journal_id.currency_id:
            currency = self.account_journal_id.currency_id
        else:
            currency = self.env.company.currency_id

        # Validamos que se cuente con tasas, de lo contrario retornemos falso
        if len(currency.rate_ids.read()) > 0:
            return sorted(currency.rate_ids.read(), key=lambda item: item["display_name"])[0]
        else:
            return False

    @api.depends('available_payment_method_line_ids')
    def _compute_payment_method_line_id(self):
        ''' Compute the 'payment_method_line_id' field.
        This field is not computed in '_compute_payment_method_line_fields' because it's a stored editable one.
        '''
        for pay in self:
            available_payment_method_lines = pay.available_payment_method_line_ids

            # Select the first available one by default.
            if pay.payment_method_line_id in available_payment_method_lines:
                pay.payment_method_line_id = pay.payment_method_line_id
            elif available_payment_method_lines:
                pay.payment_method_line_id = available_payment_method_lines[0]._origin
            else:
                pay.payment_method_line_id = False

    @api.depends('payment_type', 'account_journal_id', 'currency_id')
    def _compute_payment_method_line_fields(self):
        for pay in self:
            pay.available_payment_method_line_ids = pay.account_journal_id._get_available_payment_method_lines(pay.payment_type)
            to_exclude = pay._get_payment_method_codes_to_exclude()
            if to_exclude:
                pay.available_payment_method_line_ids = pay.available_payment_method_line_ids.filtered(lambda x: x.code not in to_exclude)

    def _get_payment_method_codes_to_exclude(self):
        # can be overriden to exclude payment methods based on the payment characteristics
        self.ensure_one()
        return []
    
    @api.onchange('payment_method_id')
    def onchange_payment_method_id_check_domain(self):
        if self.payment_method_id:
            self.check_domain = str([("l10n_latam_check_current_journal_id.inbound_payment_method_line_ids.payment_method_id.code", "in", ["new_third_party_checks", "in_third_party_checks"]), ('state', '=', 'posted')])


    # def _getSupplierCheckDomain(self):
    #     return [("l10n_latam_check_current_journal_id.inbound_payment_method_line_ids.payment_method_id.code", "in", ["new_third_party_checks", "in_third_party_checks"]), ('state', '=', 'posted')]
    # def _getCustomerCheckDomain(self):

    #     return [('payment_method_code', '=', 'new_third_party_checks'), ('l10n_latam_check_current_journal_id', '=', self.account_journal_id.id), ('state', '=', 'posted')]
