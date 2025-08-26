from odoo import _, api, fields, models, tools

import logging
_logger = logging.getLogger(__name__)


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

    # Metodo para verificar si se esta usando la misma moneda en el agrupador de pago
    def _checkSameCurrency(self):
        return self.currency_id.id == self.payment_aggregator_currency_id.id

    # Onchange para calcular el precio de la tasa
    @api.onchange('payment_amount','exchange_rate')
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