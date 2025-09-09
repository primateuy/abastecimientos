from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MPSPaymentAggregatorWizard(models.TransientModel):
    """
    Wizard para crear agregadores de pagos desde listados de facturas.

    - Este wizard recibe facturas seleccionadas y crea uno o varios
      registros de `mps.payment.aggregator` agrupando por cliente/proveedor
      y por moneda.
    - Se crean las líneas `account.move.line.payment.aggregator` partiendo
      de los apuntes (cuentas por cobrar/pagar) de las facturas.
    - Se limita la creación de líneas a las primeras 80, respetando la lógica
      implementada en el modelo del agregador.
    """
    _name = 'mps.payment.aggregator.wizard'
    _description = 'Wizard para crear agregadores de pagos desde facturas seleccionadas'

    move_ids = fields.Many2many('account.move', string='Facturas seleccionadas')
    date = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    partner_type = fields.Selection([
        ('customer', 'Cliente'),
        ('supplier', 'Proveedor'),
    ], string='Tipo de tercero', required=True)
    receipt_type = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Tipo de recibo', required=True)

    receiptbook_id = fields.Many2one(
        'mps.receipt.books',
        string='Talonario',
        required=True,
        domain="[('partner_type', '=', partner_type), ('type', '=', receipt_type), ('is_public', '=', True)]",
    )

    @api.model
    def default_get(self, fields_list):
        """
        Define valores por defecto desde el contexto del listado.
        - Determina `partner_type` en base al tipo de factura.
        - Pre-carga las facturas activas.
        - Sugiere un talonario compatible.
        """
        res = super().default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []

        if active_model == 'account.move' and active_ids:
            moves = self.env['account.move'].browse(active_ids)
            res['move_ids'] = [(6, 0, moves.ids)]

            # Inferir partner_type según el tipo de facturas del listado
            # out_invoice: clientes; in_invoice: proveedores
            move_types = set(moves.mapped('move_type'))
            if move_types <= {'out_invoice', 'out_refund'}:
                res['partner_type'] = 'customer'
                res['receipt_type'] = 'inbound'
            elif move_types <= {'in_invoice', 'in_refund'}:
                res['partner_type'] = 'supplier'
                res['receipt_type'] = 'outbound'
            else:
                # Mezcla no soportada en el mismo lote
                raise ValidationError(_("Seleccione facturas del mismo tipo (clientes o proveedores)."))

            # Sugerir talonario compatible con el partner_type
            if res.get('partner_type') and res.get('receipt_type'):
                receiptbook = self.env['mps.receipt.books'].search([
                    ('partner_type', '=', res['partner_type']),
                    ('type', '=', res['receipt_type']),
                    ('is_public', '=', True),
                ], limit=1)
                if receiptbook:
                    res['receiptbook_id'] = receiptbook.id

        return res

    def _get_receivable_payable_lines(self, moves):
        """
        Obtiene líneas contables de CxC/CxP sin conciliar para un conjunto de facturas.
        Retorna recordset de `account.move.line`.
        """
        return moves.mapped('line_ids').filtered(
            lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable'] and not l.reconciled
        )

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        """
        Ajusta el tipo de talonario según el tipo de tercero:
        - customer -> inbound
        - supplier -> outbound
        """
        if self.partner_type == 'customer':
            self.receipt_type = 'inbound'
        elif self.partner_type == 'supplier':
            self.receipt_type = 'outbound'

    def action_create_aggregators(self):
        """
        Crea agrupadores por partner y moneda a partir de las facturas seleccionadas.
        - Determina la moneda por `move.currency_id`.
        - Para cada grupo (partner, moneda) crea un `mps.payment.aggregator` con
          los campos mínimos requeridos y asigna las líneas contables.
        - Busca `account.journal.aggregator` por compañía y moneda.
        - Valida que las facturas tengan líneas de crédito disponibles antes de crear agregadores.
        """
        self.ensure_one()
        if not self.move_ids:
            raise ValidationError(_("Debe seleccionar al menos una factura."))

        # Agrupar por partner y moneda
        groups = {}
        for move in self.move_ids:
            partner = move.partner_id
            currency = move.currency_id
            key = (partner.id, currency.id)
            groups.setdefault(key, self.env['account.move'])
            groups[key] |= move

        created_aggregators = self.env['mps.payment.aggregator']
        invalid_factures = []

        for (partner_id, currency_id), grouped_moves in groups.items():
            # Obtener líneas CxC/CxP de las facturas agrupadas
            credit_lines = self._get_receivable_payable_lines(grouped_moves)
            
            # Validar que hay líneas de crédito disponibles
            if not credit_lines:
                partner_name = self.env['res.partner'].browse(partner_id).name
                currency_name = self.env['res.currency'].browse(currency_id).name
                invalid_factures.append(f"{partner_name} ({currency_name})")
                continue

            # Buscar diario intermedio para la moneda
            journal_agg = self.env['account.journal.aggregator'].search([
                ('company_id', '=', self.env.company.id),
                ('currency_id', '=', currency_id),
            ], limit=1)
            if not journal_agg:
                raise ValidationError(_("No existe un Diario Intermedio para la moneda seleccionada."))

            # Preparar valores del agregador
            vals = {
                'company_id': self.env.company.id,
                'name': _('Borrador'),
                'customer_id': partner_id,
                'currency_id': currency_id,
                'date': self.date,
                'receiptbook_id': self.receiptbook_id.id,
                'account_journal_aggregator_id': journal_agg.id,
            }

            # Pasar líneas al crear para que dispare set_account_move_line
            vals['mps_credits_line_ids'] = [(6, 0, credit_lines.ids)]

            aggregator = self.env['mps.payment.aggregator'].create(vals)
            created_aggregators |= aggregator

        # Mostrar mensaje de advertencia si hay facturas sin líneas de crédito
        if invalid_factures:
            warning_msg = _("Las siguientes facturas no tienen líneas de crédito disponibles y no se incluyeron en los agregadores:\n\n")
            warning_msg += "\n".join(invalid_factures)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': warning_msg,
                    'type': 'warning',
                    'sticky': True,
                }
            }

        # Abrir los agregadores creados
        action = {
            'name': _('Agregadores de pago creados'),
            'type': 'ir.actions.act_window',
            'res_model': 'mps.payment.aggregator',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_aggregators.ids)],
        }
        return action


