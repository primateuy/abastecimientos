from odoo import _, api, fields, models, tools

import logging
_logger = logging.getLogger(__name__)


class MPPaymentMethodsLine(models.Model):

    _name = 'mps.payment.methods.line'
    _description = 'Model to save the payment methods'
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    # importe
    payment_amount = fields.Monetary(currency_field="payment_aggregator_currency_id")
    # Moneda
    currency_id = fields.Many2one('res.currency', string='Journal Currency', compute='_compute_currencies', store=True, readonly=False)
    payment_aggregator_currency_id = fields.Many2one('res.currency', compute='_compute_currencies', store=True, readonly=False)
    # fecha
    date = fields.Date(related='mps_payment_aggregator_id.date')
    # memo
    memo = fields.Char()

    account_journal_id = fields.Many2one(
        'account.journal',
        string='Account Journal',
        # domain="['|',('type','=','cash'),('type','=','bank'),('currency_id','=',payment_aggregator_currency_id),('intermediate_diary','=',False)]"
        domain="['|',('type','=','cash'),('type','=','bank'),('intermediate_diary','=',False)]"
    )

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
        domain=lambda self: str(self._getPaymentMethodDomain()),
        default=lambda self: self._get_default_payment_method()
    )
    exchange_rate = fields.Float()
    exchange_rate_visibility = fields.Boolean(
        default=False,
        store=False
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
    check_bank = fields.Char()

    # vat
    check_vat = fields.Char()

    # Adenda
    adenda = fields.Char()

    # Metodo para asignar el dominio de los metodos de pago
    @api.onchange('account_journal_id')
    def onchange_account_journal_id(self):
        if not self.account_journal_id:
            # Generamos el domain para el metodo de pago
            self.payment_method_domain = self._generatePaymentMethodDomain()

            # Invocamos el metodo para controlar la visibilidad del tipo de pago
            self._getVisibilityPaymentType()

            # Asignamos la moneda del agrupador de pago
            self.payment_aggregator_currency_id = self._getPaymentAggregatorCurrency()
        else:
            # Establecemos el domain
            self.payment_method_domain = str(self._getPaymentMethodDomain())
        if self.account_journal_id and not self.account_journal_id.currency_id:
            self.currency_id = self.env.company.currency_id

    @api.onchange('currency_id')
    def onchange_currency_id(self):
        if self.currency_id:
            if self.payment_aggregator_currency_id:
                self.exchange_rate_visibility = self._checkSameCurrency() == False
            
            self.onchange_payment_amount()
    @api.onchange('payment_method_id')
    def onchange_payment_method_id(self):
        if self.payment_method_id:
            self.is_check = self.payment_method_id.code == "check_printing"

(self):
        if self.payment_method_id:
            self.is_check = self.payment_method_id.code == "check_printing"
    
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
                return [('id', 'in', payment_method_ids)] 
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

    def _default_rate(self):
        from_curr = self.currency_id or self.env.company.currency_id
        to_curr = self.payment_aggregator_currency_id or self.env.company.currency_id
        company = self.company_id or self.env.company
        date = self.date or fields.Date.context_today(self)
        try:
            return from_curr._get_conversion_rate(from_curr, to_curr, company, date)
        except Exception:
            # Fallback simple ratio if rates exist
            if getattr(from_curr, 'rate', False) and getattr(to_curr, 'rate', False):
                return (to_curr.rate or 1.0) / (from_curr.rate or 1.0)
            return 1.0

    @api.depends('account_journal_id', 'company_id', 'mps_payment_aggregator_id', 'mps_payment_aggregator_id.currency_id')
    def _compute_currencies(self):
        for rec in self:
            # Journal currency (fallback company)
            journal_cur = rec.account_journal_id.currency_id or (rec.company_id or rec.env.company).currency_id
            rec.currency_id = journal_cur
            # Receipt currency from aggregator/context/company
            agg_cur = False
            if rec.mps_payment_aggregator_id and hasattr(rec.mps_payment_aggregator_id, 'currency_id') and rec.mps_payment_aggregator_id.currency_id:
                agg_cur = rec.mps_payment_aggregator_id.currency_id
            elif rec.env.context.get('currency_id'):
                agg_cur = rec.env['res.currency'].browse(rec.env.context.get('currency_id'))
            else:
                agg_cur = (rec.company_id or rec.env.company).currency_id
            rec.payment_aggregator_currency_id = agg_cur
            # If same currency, normalize rate to 1 and align amounts
            if rec.currency_id and rec.payment_aggregator_currency_id and rec.currency_id == rec.payment_aggregator_currency_id:
                rec.exchange_rate = 1.0
                if rec.payment_amount:
                    rec.amount = rec.payment_amount

    @api.onchange('account_journal_id', 'company_id', 'date')
    def _onchange_currencies_and_date(self):
        for rec in self:
            # Recompute currencies
            rec._compute_currencies()
            # Set default rate when currencies defined
            if rec.currency_id and rec.payment_aggregator_currency_id:
                rec.exchange_rate = rec._default_rate()
                if rec.payment_amount:
                    rec.amount = rec.payment_amount if rec.currency_id == rec.payment_aggregator_currency_id else rec.payment_amount * rec.exchange_rate

    @api.onchange('payment_amount')
    def _onchange_payment_amount(self):
        for rec in self:
            if not rec.payment_amount:
                continue
            if rec.currency_id and rec.payment_aggregator_currency_id:
                if rec.currency_id == rec.payment_aggregator_currency_id:
                    rec.exchange_rate = 1.0
                    rec.amount = rec.payment_amount
                else:
                    if not rec.exchange_rate:
                        rec.exchange_rate = rec._default_rate()
                    rec.amount = rec.payment_amount * rec.exchange_rate

    @api.onchange('amount')
    def _onchange_amount(self):
        for rec in self:
            # Keep payment_amount as the source of truth: adjust exchange_rate accordingly
            if rec.payment_amount:
                if rec.currency_id == rec.payment_aggregator_currency_id:
                    rec.exchange_rate = 1.0
                    rec.amount = rec.payment_amount
                else:
                    rec.exchange_rate = (rec.amount or 0.0) / (rec.payment_amount or 1.0) if rec.payment_amount else rec.exchange_rate

    @api.onchange('exchange_rate')
    def _onchange_exchange_rate(self):
        for rec in self:
            if rec.payment_amount:
                if rec.currency_id == rec.payment_aggregator_currency_id:
                    rec.exchange_rate = 1.0
                    rec.amount = rec.payment_amount
                else:
                    rec.amount = rec.payment_amount * (rec.exchange_rate or 0.0)
