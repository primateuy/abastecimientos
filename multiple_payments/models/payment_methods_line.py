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

    # MODIFICACIÓN 1: Campo exchange_rate como currency_rate de account_move
    exchange_rate = fields.Float(
        string='Exchange Rate',
        digits=(16, 6),
        compute='_compute_exchange_rate',
        store=True,
        help="Exchange rate between payment currency and aggregator currency"
    )
    
    # NUEVO CAMPO: Importe en moneda del diario
    payment_currency_amount = fields.Monetary(
        string='Amount in Payment Currency',
        currency_field='currency_id',
        compute='_compute_payment_currency_amount',
        store=True,
        help="Amount converted to the payment method currency (diario currency)"
    )
    
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

    # MÉTODO NUEVO: Computar exchange_rate como currency_rate de account_move
    @api.depends('currency_id', 'payment_aggregator_currency_id', 'date', 'payment_amount', 'amount')
    def _compute_exchange_rate(self):
        """
        Computar la tasa de cambio de manera similar a currency_rate en account_move.
        Se actualiza automáticamente cuando cambian las monedas, fecha, o importes.
        """
        for record in self:
            if not record.currency_id or not record.payment_aggregator_currency_id:
                record.exchange_rate = 1.0
                continue
                
            # Si las monedas son iguales, la tasa es 1
            if record.currency_id.id == record.payment_aggregator_currency_id.id:
                record.exchange_rate = 1.0
                continue
            
            # Si hay payment_amount y amount, calcular la tasa basada en ellos
            if record.payment_amount and record.amount and record.payment_amount > 0:
                record.exchange_rate = record.amount / record.payment_amount
                continue
            
            # Si no hay importes, usar la tasa oficial de Odoo
            try:
                date = record.date or fields.Date.today()
                company = record.env.company
                
                # Obtener la tasa de conversión oficial
                converted_amount = record.currency_id._convert(
                    1.0,
                    record.payment_aggregator_currency_id,
                    company,
                    date
                )
                
                record.exchange_rate = converted_amount if converted_amount > 0 else 1.0
                
            except Exception as e:
                _logger.warning("Error computing exchange rate: %s", str(e))
                record.exchange_rate = 1.0

    # NUEVO MÉTODO: Computar importe en moneda del diario
    @api.depends('payment_amount', 'amount', 'currency_id', 'payment_aggregator_currency_id')
    def _compute_payment_currency_amount(self):
        """
        Computar el importe en la moneda del diario (moneda del método de pago).
        Este campo muestra el valor convertido a la moneda del diario.
        Fórmula: payment_amount / amount
        """
        for record in self:
            if not record.payment_amount or not record.amount or record.amount <= 0:
                record.payment_currency_amount = 0.0
                continue
            
            # Si las monedas son iguales, el importe es el mismo
            if record._checkSameCurrency():
                record.payment_currency_amount = record.payment_amount
                continue
            
            # Calcular el importe en la moneda del diario
            # Fórmula: payment_amount / amount
            # Donde payment_amount está en moneda del diario y amount en moneda del agrupador
            record.payment_currency_amount = record.payment_amount / record.amount

    # MODIFICACIÓN 2: Onchange para amount que recalcula exchange_rate
    @api.onchange('amount')
    def onchange_amount(self):
        """
        Recalcular exchange_rate cuando se modifica el campo amount.
        Este método permite al usuario modificar directamente el amount y 
        que se recalcule automáticamente la tasa de cambio.
        """
        if not self.amount or not self.payment_amount or self.payment_amount <= 0:
            return
            
        # Calcular la nueva tasa de cambio basada en amount y payment_amount
        new_exchange_rate = self.amount / self.payment_amount
        
        # Actualizar el exchange_rate directamente (sin trigger del compute)
        self._origin.exchange_rate = new_exchange_rate

    # MODIFICACIÓN 3: Onchange para exchange_rate que recalcula amount
    @api.onchange('exchange_rate')
    def onchange_exchange_rate(self):
        """
        Recalcular amount cuando se modifica el campo exchange_rate.
        Este método permite al usuario modificar directamente la tasa de cambio
        y que se recalcule automáticamente el amount.
        """
        if not self.exchange_rate or not self.payment_amount or self.exchange_rate <= 0:
            return
            
        # Calcular el nuevo amount basado en payment_amount y exchange_rate
        new_amount = self.payment_amount * self.exchange_rate
        
        # Actualizar el amount directamente
        self.amount = new_amount

    # Metodo para asignar el dominio de los metodos de pago
    @api.onchange('account_journal_id')
    def onchange_account_journal_id(self):
        if not self.account_journal_id:
            # Generamos el domain para el metodo de pago
            self.payment_method_domain = "[('id', 'in', %s), ('payment_method_id.code', '!=', 'in_third_party_checks')]" % self.available_payment_method_line_ids.ids

            # Invocamos el metodo para controlar la visibilidad del tipo de pago
            self._getVisibilityPaymentType()

            # Asignamos la moneda del agrupador de pago
            self.payment_aggregator_currency_id = self._getPaymentAggregatorCurrency()

            self.have_journal_currency = False
        else:
            # Establecemos el domain
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
                    # CORREGIDO: Usar el método mejorado para obtener tasa
                    self._compute_exchange_rate_auto()
            
            # Recalcular el importe con la nueva moneda
            self.onchange_payment_amount()

    # MÉTODO CORREGIDO: Verificar si se usa la misma moneda
    def _checkSameCurrency(self):
        """Verificar si la moneda del método de pago es igual a la del agrupador"""
        if not self.currency_id or not self.payment_aggregator_currency_id:
            return True
        return self.currency_id.id == self.payment_aggregator_currency_id.id

    # MÉTODO NUEVO: Calcular tasa de cambio automáticamente
    def _compute_exchange_rate_auto(self):
        """Calcular la tasa de cambio usando los métodos oficiales de Odoo"""
        if self._checkSameCurrency():
            self.exchange_rate = 1.0
            return

        try:
            # Usar el método oficial de conversión de Odoo para obtener la tasa
            date = self.date or fields.Date.today()
            company = self.env.company
            
            # Convertir 1 unidad de la moneda de pago a la moneda del agrupador
            converted_amount = self.currency_id._convert(
                1.0,
                self.payment_aggregator_currency_id,
                company,
                date
            )
            
            self.exchange_rate = converted_amount if converted_amount > 0 else 1.0
            
        except Exception as e:
            _logger.warning("Error calculating exchange rate: %s", str(e))
            self.exchange_rate = 1.0

    # MODIFICACIÓN 4: Onchange mejorado para payment_amount
    @api.onchange('payment_amount')
    def onchange_payment_amount(self):
        """
        Recalcular importes cuando cambia el monto del pago.
        Este método actualiza tanto amount como exchange_rate cuando se modifica payment_amount.
        """
        
        # Si no hay monto de pago, limpiar el importe
        if not self.payment_amount:
            self.amount = 0
            return
        
        # Si las monedas son iguales, no hay conversión
        if self._checkSameCurrency():
            self.amount = self.payment_amount
            self.exchange_rate = 1.0
            return
        
        # Si hay conversión de monedas
        if self.exchange_rate and self.exchange_rate > 0:
            try:
                # Usar el método oficial de conversión de Odoo
                date = self.date or fields.Date.today()
                company = self.env.company
                
                # Convertir el monto de pago a la moneda del agrupador
                self.amount = self.currency_id._convert(
                    self.payment_amount,
                    self.payment_aggregator_currency_id,
                    company,
                    date
                )
                
                # Actualizar la tasa de cambio basada en la conversión real
                if self.payment_amount > 0:
                    self._origin.exchange_rate = self.amount / self.payment_amount
                
            except Exception as e:
                _logger.warning("Error in currency conversion: %s", str(e))
                # Fallback: usar cálculo manual
                self.amount = self.payment_amount * self.exchange_rate
        else:
            # Recalcular la tasa automáticamente
            self._compute_exchange_rate_auto()
            # Y luego calcular el importe
            if self.exchange_rate > 0:
                self.amount = self.payment_amount * self.exchange_rate

    # Onchange para detectar si el metodo de pago es cheques
    @api.onchange('payment_method_id')
    def onchange_payment_method_id(self):
        if self.payment_method_id:
            self.is_check = self.payment_method_id.code in check_codes
    
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
            if aggregator_currency and self.currency_id and aggregator_currency.id == self.currency_id.id:
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

    # MÉTODO CORREGIDO: Obtener tasa de cambio usando métodos oficiales de Odoo
    def _getCurrencyRate(self):
        """Obtener la tasa de cambio más reciente usando métodos oficiales de Odoo"""
        aggregator_currency = self._getPaymentAggregatorCurrency()
        
        if not aggregator_currency or not self.currency_id:
            return {"inverse_company_rate": 1.0}
        
        if aggregator_currency.id == self.currency_id.id:
            return {"inverse_company_rate": 1.0}
        
        try:
            date = self.date or fields.Date.today()
            company = self.env.company
            
            # Usar el método oficial de Odoo para convertir
            converted_amount = self.currency_id._convert(
                1.0,
                aggregator_currency,
                company,
                date
            )
            
            return {"inverse_company_rate": converted_amount if converted_amount > 0 else 1.0}
            
        except Exception as e:
            _logger.warning("Error getting currency rate: %s", str(e))
            return {"inverse_company_rate": 1.0}

    @api.depends('available_payment_method_line_ids')
    def _compute_payment_method_line_id(self):
        ''' Compute the 'payment_method_line_id' field.
        This field is not computed in '_compute_payment_method_line_fields' because it's a stored editable one.
        '''
        for pay in self:
            available_payment_method_lines = pay.available_payment_method_line_ids

            # CORREGIDO: Solo asignar valor por defecto si no hay selección previa
            # Preservar la selección del usuario cuando sea válida
            if pay.payment_method_line_id in available_payment_method_lines:
                # Mantener la selección actual si es válida
                pay.payment_method_line_id = pay.payment_method_line_id
            elif not pay.payment_method_line_id and available_payment_method_lines:
                # Solo asignar por defecto si no hay selección previa
                pay.payment_method_line_id = available_payment_method_lines[0]._origin
            elif pay.payment_method_line_id and pay.payment_method_line_id not in available_payment_method_lines:
                # Si la selección actual no es válida, limpiar el campo
                pay.payment_method_line_id = False
            else:
                # Mantener el estado actual
                pass

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

    # MÉTODO NUEVO: Validar que los datos estén correctos antes de crear pagos
    def validate_currency_data(self):
        """Validar que los datos de moneda y conversión sean correctos"""
        errors = []
        
        if not self.payment_amount or self.payment_amount <= 0:
            errors.append(_("Payment amount must be greater than zero"))
        
        if not self.amount or self.amount <= 0:
            errors.append(_("Converted amount must be greater than zero"))
        
        if not self._checkSameCurrency():
            if not self.exchange_rate or self.exchange_rate <= 0:
                errors.append(_("Exchange rate must be greater than zero when using different currencies"))
        
        if not self.currency_id:
            errors.append(_("Payment method currency must be defined"))
        
        if not self.payment_aggregator_currency_id:
            errors.append(_("Payment aggregator currency must be defined"))
            
        return errors