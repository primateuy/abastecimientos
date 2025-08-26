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
        # Lineas de pago
        for payment_method in self.mps_payment_methods_line_ids:
            # Tomamos el diario de la linea de pago
            journal = payment_method.account_journal_id
            
            # Validamos
            if not journal:
                raise UserError(_("La linea de pago debe contener un diario contable"))
            
            # Construimos el diccionario para el pago
            payment_details = self._get_standard_payment()
            payment_details['date'] = payment_method["date"]
            payment_details['amount'] = payment_method["amount"]
            payment_details['payment_type'] = self["receiptbook_id"]["type"] if not self["receiptbook_id"]["enable_reverse_payment"] else payment_method["payment_type"]
            payment_details['is_internal_transfer'] = True   # Marcamos
            payment_details['ref'] = _('Internal Transfer')   # Referencia
            payment_details['payment_method_id'] = payment_method["payment_method_id"]["id"]
            
            # Validar el sentido del talonario para registrar el pago, ya sea saliente o entrante
            if self.receiptbook_id.type == "outbound":
                # payment_details['journal_id'] = self.currency_id.account_journal_id.id # Diario origen
                # payment_details['destination_journal_id'] = journal.id # Diario destino

                payment_details['journal_id'] = journal.id # Diario origen
                payment_details['destination_journal_id'] = self.currency_id.account_journal_id.id,
            else:
                payment_details['journal_id'] = journal.id # Diario origen
                payment_details['destination_journal_id'] = self.currency_id.account_journal_id.id, # Diario destino
            
            # Creamos el pago
            self.create_publish_payment(payment_details)

    # Metodo para crear el pago a cuenta
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
        if not payment_details:
            raise ValidationError(_("Payments cannot be created with empty information."))
        # Creamos las transferencias internas
        payment_id = self.env['account.payment'].create(payment_details)
        # Confirmamos el pago
        payment_id.action_post()
        payment_id.set_transaction_type()
        payment_id.line_ids.payment_aggregator_id = self.id

        # Retornamos el pago
        return payment_id

    # Se calcula la diferencia
    @api.depends('amount', 'payment_account', 'debt_allocation')
    def _compute_difference(self):
        for record in self:
            record.difference = record.amount - (record.payment_account + record.debt_allocation)
    # Calculamos debt_allocation automáticamente cuando cambian las líneas
    @api.depends('account_move_line_payment_agg_ids.payment_aggregator_total_import')
    def _compute_debt_allocation(self):
        for record in self:
            totals = record.account_move_line_payment_agg_ids.mapped('payment_aggregator_total_import') or []
            record.debt_allocation = sum(totals)
            # do NOT assign to m2m/o2m children here; use related fields if needed

    
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
        
        # Buscar la vista específica si existe
        view_id = self.env.ref('multiple_payments.view_account_payment_tree_grouped_simple', False)
        
        return {
            'name': 'Pagos Agrupados',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'context': {
                'group_by': ['transaction_type'],
                'search_default_partner_id': self.customer_id.id if self.customer_id else False,
            },
            'domain': [('payment_aggregator_id', '=', self.id)]
        }
    
    def button_update_accounting_notes(self):
        self.filter_credit_moves()
        return
    
    # Accion del boton de eliminacion de cuentas en 0
    def button_delete_accounting_notes(self):
        # Metodo para eliminar los registros donde total_import es 0
        self._delete_accounting_notes()
        return
    
    def _delete_accounting_notes(self):
        # Filtrar solo los registros donde total_import es 0
        lines_to_remove = self.account_move_line_payment_agg_ids.filtered(lambda line: line.payment_aggregator_total_import == 0)
        # Eliminar solo esas líneas
        self.write({'account_move_line_payment_agg_ids': [(3, line.id) for line in lines_to_remove]})
        return True

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
