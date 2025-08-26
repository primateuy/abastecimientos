from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
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
        required=True
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

    # Cambiar estatus del registro
    
    # Cambiar estatus del registro
    def button_change_state(self):
        if self.state == "draft":
            # Validamos pagos
            if len(self.mps_payment_methods_line_ids) == 0:
                raise ValidationError(_("To make payments you must load the payments in the payment lines."))

            try:
                # Recorrer los créditos y/o débitos
                self._create_invoices_payment()

                # Validamos si tiene pago a cuenta para realizar el pago
                self._create_payment_acount()

                # Crear los pagos de los métodos de pago
                self._create_lines_payment_payments()

            except Exception as e:
                raise UserError(e)
            self.state = "published"
        else:
            self.state = "draft"

    # --- Button actions referenced by the form view ---
    def button_open_accounting_notes(self):
        """ Placeholder action to satisfy the view; replace with a real action if needed. """
        self.ensure_one()
        return {'type': 'ir.actions.act_window_close'}

    def button_open_grouped_payments(self):
        """ Placeholder action to satisfy the view; replace with a real action if needed. """
        self.ensure_one()
        return {'type': 'ir.actions.act_window_close'}

# Metodo para crear los pagos de las lineas de pago



    # --- Button actions referenced by the form view ---
        def button_open_accounting_notes(self):
            """ Placeholder action to satisfy the view; replace with a real action if needed. """
            self.ensure_one()
            return {'type': 'ir.actions.act_window_close'}
    
        def button_open_grouped_payments(self):
            """ Placeholder action to satisfy the view; replace with a real action if needed. """
            self.ensure_one()
            return {'type': 'ir.actions.act_window_close'}
    def _create_lines_payment_payments(self):
        # Por cada línea de método, crear una transferencia interna
        for line in self.mps_payment_methods_line_ids:
            journal = line.account_journal_id
            if not journal:
                raise UserError(_("La linea de pago debe contener un diario contable"))

            vals = self._get_standard_payment()
            vals.update({
                'date': line.date,
                'is_internal_transfer': True,
                'ref': _('Internal Transfer'),
                'payment_method_id': line.payment_method_id.id if line.payment_method_id else False,
            })

            if self.receiptbook_id.type == "inbound":
                # ORIGEN = diario de la moneda del recibo
                vals['journal_id'] = self.currency_id.account_journal_id.id
                # DESTINO = diario de la línea
                vals['destination_journal_id'] = journal.id

                # Monto en moneda del ORIGEN (moneda del recibo)
                vals['amount'] = line.amount or 0.0
                vals['currency_id'] = self.currency_id.id
            else:
                # ORIGEN = diario de la línea
                vals['journal_id'] = journal.id
                # DESTINO = diario de la moneda del recibo
                vals['destination_journal_id'] = self.currency_id.account_journal_id.id

                # Monto en moneda del ORIGEN (moneda del diario de la línea)
                vals['amount'] = line.payment_amount or 0.0
                vals['currency_id'] = (line.currency_id or self.company_id.currency_id).id

            # Crear y postear la transferencia interna
            self.create_publish_payment(vals)

    # --- Button actions referenced by the form view ---
    def button_open_accounting_notes(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window_close'}

    def button_open_grouped_payments(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window_close'}
