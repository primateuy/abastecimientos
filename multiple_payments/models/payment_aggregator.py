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
    def button_change_state(self):
        if self.state == "draft":
           
            # Validamos pagos
            if len(self.mps_payment_methods_line_ids) == 0:
                raise ValidationError(_("To make payments you must load the payments in the payment lines."))

           
            try:
                # Recorrer los creditos y/o debitos
                self._create_invoices_payment()

                # Validamos si tiene pago a cuenta para realizar el pago
                self._create_payment_acount()

                # Crear los pagos de los metodos de pago
                self._create_lines_payment_payments()

            except Exception as e:
                raise UserError(e)
            self.state = "published"
        else:
            self.state = "draft"

    # Metodo para crear los pagos de las lineas de pago
    
    
def _create_lines_payment_payments(self):
    """
    Por cada línea de método crea SOLO la transferencia interna OUTBOUND
    (Odoo crea la contraparte IN automáticamente).
    - Sin partner
    - is_internal_transfer=True
    - partner_type='supplier' (NOT NULL en v16)
    """
    for line in self.mps_payment_methods_line_ids:
        journal = line.account_journal_id
        if not journal:
            raise UserError(_("La linea de pago debe contener un diario contable"))

        # Origen/destino y montos
        if self.receiptbook_id.type == "inbound":
            origin_journal = self.currency_id.account_journal_id
            dest_journal = journal
            origin_currency = self.currency_id
            origin_amount = line.amount or 0.0
        else:
            origin_journal = journal
            dest_journal = self.currency_id.account_journal_id
            origin_currency = (line.currency_id or self.company_id.currency_id)
            origin_amount = line.payment_amount or 0.0

        vals = self._get_standard_payment()
        vals.update({
            'date': line.date,
            'journal_id': origin_journal.id,
            'is_internal_transfer': True,
            'destination_journal_id': dest_journal.id,
            'payment_type': 'outbound',       # correcto v16
            'partner_id': False,              # sin tercero
            'partner_type': 'supplier',       # NOT NULL constraint
            'amount': origin_amount,
            'currency_id': origin_currency.id,
            'ref': _('Internal Transfer'),
            'payment_method_id': line.payment_method_id.id if line.payment_method_id else False,
        })
        self.create_publish_payment(vals)


    def _create_payment_acount(self):
        if self.payment_account > 0:
            # Armamos los detalles del pago
            payment_details = self._get_standard_payment()

            # Modificamos el monto a pagar
            payment_details['amount'] = self.payment_account

            # Creamos el pago
            self.create_publish_payment(payment_details)

    # Metodo para recorrer los apuntes contables y marcar como pagados
    def _create_invoices_payment(self):
        if self.account_move_line_payment_agg_ids:
            # Borramos las deudas que tengan importe 0
            self._delete_accounting_notes()

            # Si todavia hay deudas por pagar
            if len(self.account_move_line_payment_agg_ids) > 0:
                # Recorrer los creditos y/o debitos
                for credit_line in self.account_move_line_payment_agg_ids:
                    # Armamos los detalles del pago
                    payment_details = self._get_standard_payment()

                    # Modificamos los campos necesarios
                    payment_details["amount"] = credit_line.payment_aggregator_total_import  # Monto a pagar
                    # payment_details["reconciled_invoice_ids"] = [(6,0,[credit_line.move_id.id])], # Se asigna la factura al pago
                    payment_details["ref"] = credit_line.move_id.name # Nombre de referencia

                    # Creamos el pago
                    move_id = self.create_publish_payment(payment_details)

                    # Invocamos el metodo para reconciliar el estatus del pago
                    move_id._compute_reconciliation_status()

                    # Obtenemos los apuntes contables del pago
                    payment_lines = move_id.line_ids.filtered(
                        lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
                    )
                    # Obtenemos los apuntes contables de la factura
                    invoice_lines = credit_line.move_id.line_ids.filtered(
                        lambda line: line.account_id.account_type in ['asset_receivable', 'liability_payable'] and not line.reconciled
                    )
                    # Unimos en una sola lista del mismo modelo e invocamos el metodo reconcile para 
                    # reconciliar el pago de la factura
                    (invoice_lines + payment_lines).reconcile()

                    # Marcamos los pagos como matches
                    for payment_line in payment_lines:
                        if payment_line.move_id.payment_id:
                            payment_line.move_id.payment_id.is_matched = True

                    # Invocamos el metodo que comprueba si la factura puede pasar a pagada
                    credit_line.move_id._compute_payment_state()

    # Metodo para obtener el diccionario estandar para registrar un pago
    def _get_standard_payment(self):
        return {
            'partner_id': self.customer_id.id,   # Cliente
            'date': self.date,                   # Fecha del pago    
            'amount': 0,                         # Monto a pagar
            'is_internal_transfer': False,       # Si es transferencia
            'payment_type': self.receiptbook_id.type,  # Tipo de pago segun el talonario
            'journal_id': self.currency_id.account_journal_id.id, # Diario intermedio
            'partner_type': self.receiptbook_id.partner_type, # Si es cliente o si es proveedor
            'payment_method_id': self.env.ref('account.account_payment_method_manual_in').id, # Metodo de pago
            'payment_aggregator_id': self.id
        }

    # Metodo para crear un pago y publicarlo
    
def create_publish_payment(self, payment_details):
    """Crear y postear el pago; si existe el helper set_transaction_type, llamarlo."""
    if not payment_details:
        raise ValidationError(_("Payments cannot be created with empty information."))
    payment = self.env['account.payment'].create(payment_details)
    payment.action_post()
    if hasattr(payment, 'set_transaction_type'):
        payment.set_transaction_type()
    return payment

    def _compute_difference(self):
        for record in self:
            record.difference = record.amount - (record.payment_account + record.debt_allocation)
    # Calculamos debt_allocation automáticamente cuando cambian las líneas
    @api.depends('account_move_line_payment_agg_ids.payment_aggregator_total_import')
    def _compute_debt_allocation(self):
        for record in self:
            record.debt_allocation = sum(record.account_move_line_payment_agg_ids.mapped('payment_aggregator_total_import'))
            total_payments = sum(record.account_move_line_payment_agg_ids.mapped('payment_aggregator_total_import'))
        for line in record.mps_credits_line_ids:
            line.total_import = total_payments

    
    @api.onchange('customer_id', 'currency_id')
    def filter_credit_moves(self):
        self.mps_credits_line_ids = self.search_account_move_line()
        self.set_account_move_line(self.mps_credits_line_ids)

    def assign_domain(self, payment_state='not_paid'):

        return [
                    ('partner_id', '=', self.customer_id.id),
                    ('currency_id', '=', self.currency_id.id),
                    ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
                    # ('move_id.payment_state','=', payment_state),
                    ('move_id.move_type', 'in', ['out_invoice','in_invoice'])
                ]
    
    def search_account_move_line(self):
        return self.env['account.move.line'].search(self.assign_domain())
    
    def set_account_move_line(self, credit_lines=False):
        aggregator_ids = []
        if credit_lines:
            for credit_line in credit_lines:
                aggregator_record = self.env['account.move.line.payment.aggregator'].create({
                    'account_move_line_id': credit_line.id,
                    'move_id': credit_line.move_id.id,
                    'payment_aggregator_amount_currency': credit_line.amount_currency,
                    'payment_aggregator_amount_residual': credit_line.amount_residual
                })
                aggregator_ids.append(aggregator_record.id)
        self.account_move_line_payment_agg_ids = [(6, 0, aggregator_ids)]
    
    def button_open_accounting_notes(self):
        self.ensure_one()
        move_ids = self.env['account.move.line'].search([('payment_aggregator_id', '=', self.id)])
        # _logger.info(move_ids)
        return {
        'name': 'Asientos Contables',
        'type': 'ir.actions.act_window',
        'res_model': 'account.move.line',
        'view_mode': 'tree,form',
        'domain': [('id', 'in', move_ids.ids)],
        'context': {
                'group_by': ['journal_id'],
            },
        
    }
    
    
    
def button_open_grouped_payments(self):
    self.ensure_one()
    return {
        'type': 'ir.actions.act_window',
        'name': _('Pagos Agrupados'),
        'res_model': 'account.payment',
        'view_mode': 'tree,form',
        'domain': [('payment_aggregator_id', '=', self.id)],
        'context': {'group_by': ['transaction_type']},
    }


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
        values['company_id'] = self.env.company.id
        result = super().create(values)
        result.name = self.env['ir.sequence'].next_by_code('aggregator.sequence')
        return result

    def button_update_accounting_notes(self):
        """Stub added to keep legacy buttons working."""
        self.ensure_one()
        return True

    def button_delete_accounting_notes(self):
        """Stub added to keep legacy buttons working."""
        self.ensure_one()
        return True

    def _delete_accounting_notes(self):
        """Legacy stub: no-op to keep buttons working."""
        self.ensure_one()
        return True

    def _update_accounting_notes(self):
        """Legacy stub: no-op to keep buttons working."""
        self.ensure_one()
        return True

    def _open_accounting_notes(self):
        """Legacy stub: no-op to keep buttons working."""
        self.ensure_one()
        return True


def button_open_accounting_notes(self):
    self.ensure_one()
    # Stub para compatibilidad; implementar lógica real si hace falta
    return True



def button_open_grouped_payments(self):
    self.ensure_one()
    return {
        'type': 'ir.actions.act_window',
        'name': _('Pagos Agrupados'),
        'res_model': 'account.payment',
        'view_mode': 'tree,form',
        'domain': [('payment_aggregator_id', '=', self.id)],
        'context': {'group_by': ['transaction_type']},
    }



def button_update_accounting_notes(self):
    self.ensure_one()
    # Stub para compatibilidad; implementar lógica real si hace falta
    return True


def button_delete_accounting_notes(self):
    self.ensure_one()
    # Stub para compatibilidad; implementar lógica real si hace falta
    return True


def button_apply_fifo(self):
    self.ensure_one()
    # Stub para compatibilidad; implementar lógica real si hace falta
    return True


def button_assign_all(self):
    self.ensure_one()
    # Stub para compatibilidad; implementar lógica real si hace falta
    return True


def _delete_accounting_notes(self):
    self.ensure_one()
    return True


def _update_accounting_notes(self):
    self.ensure_one()
    return True


def _open_accounting_notes(self):
    self.ensure_one()
    return True
