from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class MPSPaymentAggregatorAddInvoicesWizard(models.TransientModel):
    """
    Wizard para agregar facturas a un agrupador de pagos existente.
    
    - Este wizard muestra facturas disponibles del mismo partner y moneda
      que el agrupador actual.
    - Permite seleccionar múltiples facturas para agregar al agrupador.
    - Valida que las facturas no estén pagadas y tengan líneas de crédito.
    """
    _name = 'mps.payment.aggregator.add.invoices.wizard'
    _description = 'Wizard para agregar facturas a un agrupador de pagos existente'

    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='Agrupador de Pago',
        required=True,
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        related='payment_aggregator_id.customer_id',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='payment_aggregator_id.currency_id',
        readonly=True
    )
    partner_type = fields.Selection([
        ('customer', 'Cliente'),
        ('supplier', 'Proveedor'),
    ], string='Tipo de tercero',
        related='payment_aggregator_id.receiptbook_id.partner_type',
        readonly=True
    )
    # Campo para mostrar las facturas asociadas a las líneas de crédito
    move_ids = fields.Many2many(
        'account.move',
        string='Facturas disponibles',
        compute='_compute_move_ids',
        store=False
    )
    # Campo interno para almacenar las líneas de crédito (no visible en la vista)
    move_line_ids = fields.Many2many(
        'account.move.line',
        string='Líneas de crédito disponibles',
        compute='_compute_move_line_ids',
        store=False
    )
    move_types = fields.Char(
        string='Tipos de factura',
        compute='_compute_move_types',
        store=True
    )

    @api.depends('partner_type')
    def _compute_move_types(self):
        """
        Calcula los tipos de factura según el tipo de partner.
        """
        for record in self:
            if record.partner_type == 'customer':
                record.move_types = "out_invoice,out_refund"
            elif record.partner_type == 'supplier':
                record.move_types = "in_invoice,in_refund"
            else:
                record.move_types = ""

    @api.depends('payment_aggregator_id', 'partner_id', 'currency_id', 'partner_type')
    def _compute_move_line_ids(self):
        """
        Calcula las líneas de crédito disponibles basándose en el agrupador y filtros.
        """
        for record in self:
            if record.payment_aggregator_id and record.partner_id and record.currency_id and record.partner_type:
                # Usar el método _get_available_credit_lines para obtener las líneas válidas
                available_lines = record._get_available_credit_lines(record.payment_aggregator_id)
                record.move_line_ids = [(6, 0, available_lines.ids)]
            else:
                record.move_line_ids = [(6, 0, [])]

    @api.depends('move_line_ids')
    def _compute_move_ids(self):
        """
        Calcula las facturas disponibles basándose en las líneas de crédito.
        """
        for record in self:
            if record.move_line_ids:
                # Obtener las facturas únicas de las líneas de crédito
                invoices = record.move_line_ids.mapped('move_id')
                record.move_ids = [(6, 0, invoices.ids)]
            else:
                record.move_ids = [(6, 0, [])]

    @api.onchange('partner_id', 'currency_id', 'partner_type')
    def _onchange_filters(self):
        """
        Actualiza las líneas de crédito disponibles cuando cambian los filtros.
        El campo move_line_ids es computado, por lo que se actualiza automáticamente.
        """
        # El campo move_line_ids es computado y se actualiza automáticamente
        # cuando cambian los campos en los que depende
        pass

    @api.model
    def default_get(self, fields_list):
        """
        Define valores por defecto desde el contexto del agrupador.
        """
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        existing_line_ids = self.env.context.get('existing_line_ids', [])
        
        if active_id:
            aggregator = self.env['mps.payment.aggregator'].browse(active_id)
            res['payment_aggregator_id'] = aggregator.id
            res['partner_id'] = aggregator.customer_id.id
            res['currency_id'] = aggregator.currency_id.id
            res['partner_type'] = aggregator.receiptbook_id.partner_type if aggregator.receiptbook_id else 'customer'
            
            # Log para debug
            _logger.info(f"=== DEFAULT_GET WIZARD ===")
            _logger.info(f"Active ID: {active_id}")
            _logger.info(f"Existing line IDs from context: {existing_line_ids}")
            _logger.info(f"Aggregator credits lines: {len(aggregator.mps_credits_line_ids)}")
            _logger.info(f"Aggregator credits lines IDs: {aggregator.mps_credits_line_ids.ids}")
            
            # El campo move_line_ids es computado y se calculará automáticamente
            # basándose en los valores de los campos relacionados
        
        return res

    def _get_available_credit_lines(self, aggregator):
        """
        Obtiene líneas de crédito disponibles para agregar al agrupador.
        Usa la misma lógica que el payment aggregator para encontrar líneas válidas.
        Filtra por las cuentas configuradas en el diario del talonario para la moneda.
        
        Args:
            aggregator: Recordset del agrupador de pagos
            
        Returns:
            Recordset de líneas de crédito disponibles
        """
        _logger.info(f"=== FILTRANDO LÍNEAS DE CRÉDITO PARA AGRUPADOR {aggregator.name} ===")
        
        # Usar el mismo domain que el payment aggregator
        domain = aggregator.assign_domain()
        
        _logger.info(f"Domain de búsqueda: {domain}")
        
        # Buscar líneas de crédito usando el mismo método que el aggregator
        credit_lines = self.env['account.move.line'].search(domain)
        
        _logger.info(f"Líneas de crédito encontradas: {len(credit_lines)}")
        
        if credit_lines:
            _logger.info(f"Primeras 5 líneas encontradas: {credit_lines[:5].mapped('display_name')}")
        
        # Obtener cuentas configuradas en el diario del talonario para la moneda
        journal_accounts = []
        if aggregator.receiptbook_id and aggregator.receiptbook_id.account_journal_id:
            journal = aggregator.receiptbook_id.account_journal_id
            _logger.info(f"Diario del talonario: {journal.name}")
            
            # Buscar cuentas de la moneda en el diario
            if hasattr(journal, 'account_currency_ids'):
                currency_accounts = journal.account_currency_ids.filtered(
                    lambda acc: acc.currency_id == aggregator.currency_id
                )
                journal_accounts = currency_accounts.ids
                _logger.info(f"Cuentas de moneda en diario: {[acc.display_name for acc in currency_accounts]}")
            else:
                # Si no hay account_currency_ids, usar las cuentas por defecto del diario
                if aggregator.receiptbook_id.partner_type == 'customer':
                    journal_accounts = [journal.default_account_id.id] if journal.default_account_id else []
                else:
                    journal_accounts = [journal.default_account_id.id] if journal.default_account_id else []
                _logger.info(f"Cuenta por defecto del diario: {journal.default_account_id.display_name if journal.default_account_id else 'Ninguna'}")
        
        _logger.info(f"IDs de cuentas para filtrar: {journal_accounts}")
        
        # Filtrar por cuentas del diario si están configuradas
        if journal_accounts:
            credit_lines = credit_lines.filtered(lambda l: l.account_id.id in journal_accounts)
            _logger.info(f"Líneas después de filtrar por cuentas del diario: {len(credit_lines)}")
        else:
            _logger.info("No hay cuentas del diario configuradas, usando todas las líneas de crédito")
        
        # Si no se encontraron líneas después del filtrado por cuentas, usar todas las líneas de crédito
        if not credit_lines:
            _logger.info("No se encontraron líneas con las cuentas del diario, usando todas las líneas de crédito")
            credit_lines = self.env['account.move.line'].search(domain)
        
        # Obtener líneas existentes del contexto o del agrupador
        existing_line_ids = self.env.context.get('existing_line_ids', [])
        if not existing_line_ids:
            # Fallback: usar las líneas del agrupador directamente
            existing_line_ids = aggregator.mps_credits_line_ids.ids
        
        _logger.info(f"Líneas ya en agrupador (contexto): {len(existing_line_ids)}")
        _logger.info(f"IDs de líneas ya en agrupador: {existing_line_ids}")
        
        # Filtrar líneas que ya están en el agrupador
        available_lines = credit_lines.filtered(lambda l: l.id not in existing_line_ids)
        
        _logger.info(f"Líneas disponibles (excluyendo ya agregadas): {len(available_lines)}")
        # _logger.info(f"Líneas que se mostrarán en el listado: {available_lines.mapped('display_name')}")
        
        return available_lines

    def action_search_invoices(self):
        """
        Abre el listado de facturas disponibles para selección.
        """
        self.ensure_one()
        
        _logger.info(f"=== BUSCANDO FACTURAS PARA AGRUPADOR {self.payment_aggregator_id.name} ===")
        
        # Obtener las facturas disponibles
        available_lines = self._get_available_credit_lines(self.payment_aggregator_id)
        available_invoices = available_lines.mapped('move_id')
        
        _logger.info(f"Facturas disponibles encontradas: {len(available_invoices)}")
        
        # Crear un filtro personalizado para mostrar solo estas facturas
        domain = [('id', 'in', available_invoices.ids)]
        
        action = {
            'name': f'Facturas Disponibles - {self.payment_aggregator_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree',
            'view_id': self.env.ref('multiple_payments.view_mps_payment_aggregator_invoices_checkbox_list').id,
            'target': 'current',
            'domain': domain,
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_currency_id': self.currency_id.id,
                'default_move_type': 'out_invoice' if self.partner_type == 'customer' else 'in_invoice',
                'wizard_id': self.id,  # Para poder volver al wizard
                'create': False,
                'edit': False,
                'delete': False,
            }
        }
        
        return action

    def action_add_selected_invoices(self, invoice_ids):
        """
        Agrega las facturas seleccionadas desde el listado al agrupador.
        Este método se llama desde el listado de facturas.
        
        Args:
            invoice_ids: Lista de IDs de facturas seleccionadas
        """
        self.ensure_one()
        
        if not invoice_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _("No se seleccionaron facturas."),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Obtener las facturas seleccionadas
        selected_invoices = self.env['account.move'].browse(invoice_ids)
        
        _logger.info(f"=== AGREGANDO FACTURAS SELECCIONADAS DESDE LISTADO ===")
        _logger.info(f"Facturas seleccionadas: {selected_invoices.mapped('name')}")
        
        # Obtener las líneas de crédito de las facturas seleccionadas
        available_lines = self._get_available_credit_lines(self.payment_aggregator_id)
        credit_lines = available_lines.filtered(lambda line: line.move_id in selected_invoices)
        
        _logger.info(f"Líneas de crédito de las facturas seleccionadas: {len(credit_lines)}")
        
        if not credit_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("Las facturas seleccionadas no tienen líneas de crédito disponibles."),
                    'type': 'error',
                    'sticky': False,
                }
            }
        
        # Validar que las líneas tengan montos pendientes
        invalid_lines = []
        valid_lines = self.env['account.move.line']
        
        for line in credit_lines:
            if line.amount_residual == 0 or line.reconciled:
                invalid_lines.append(f"{line.move_id.name} - {line.display_name}")
                _logger.info(f"Línea {line.display_name}: NO VÁLIDA - ya reconciliada o sin monto pendiente")
            else:
                valid_lines |= line
                _logger.info(f"Línea {line.display_name}: VÁLIDA - monto pendiente: {line.amount_residual}")
        
        if invalid_lines:
            line_names = ', '.join(invalid_lines)
            _logger.warning(f"Líneas inválidas detectadas: {line_names}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("Las siguientes líneas no tienen montos pendientes disponibles:\n\n%s") % line_names,
                    'type': 'error',
                    'sticky': False,
                }
            }
        
        # Agregar las líneas válidas al agrupador
        if valid_lines:
            _logger.info(f"Agregando {len(valid_lines)} líneas de crédito de {len(selected_invoices)} facturas al agrupador")
            
            # Agregar las líneas de crédito al agrupador
            self.payment_aggregator_id.mps_credits_line_ids = [(4, line.id) for line in valid_lines]
            
            # Crear registros de agregador para las nuevas líneas
            self.payment_aggregator_id.set_account_move_line(valid_lines)
            
            _logger.info(f"Facturas agregadas exitosamente: {selected_invoices.mapped('name')}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _("Se agregaron %d facturas (%d líneas de crédito) al agrupador de pagos.") % (len(selected_invoices), len(valid_lines)),
                    'type': 'success',
                    'sticky': False,
                }
            }
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Error'),
                'message': _("No se pudieron agregar las facturas seleccionadas."),
                'type': 'error',
                'sticky': False,
            }
        }

    def action_add_invoices(self):
        """
        Agrega las facturas seleccionadas al agrupador actual.
        """
        self.ensure_one()
        
        _logger.info(f"=== AGREGANDO FACTURAS AL AGRUPADOR {self.payment_aggregator_id.name} ===")
        _logger.info(f"Facturas seleccionadas: {self.move_ids.mapped('name')}")
        
        if not self.move_ids:
            raise ValidationError(_("Debe seleccionar al menos una factura."))
        
        # Obtener las líneas de crédito de las facturas seleccionadas
        selected_invoices = self.move_ids
        credit_lines = self.move_line_ids.filtered(
            lambda line: line.move_id in selected_invoices
        )
        
        _logger.info(f"Líneas de crédito de las facturas seleccionadas: {len(credit_lines)}")
        
        # Validar que las líneas tengan montos pendientes
        invalid_lines = []
        valid_lines = self.env['account.move.line']
        
        for line in credit_lines:
            if line.amount_residual == 0 or line.reconciled:
                invalid_lines.append(f"{line.move_id.name} - {line.display_name}")
                _logger.info(f"Línea {line.display_name}: NO VÁLIDA - ya reconciliada o sin monto pendiente")
            else:
                valid_lines |= line
                _logger.info(f"Línea {line.display_name}: VÁLIDA - monto pendiente: {line.amount_residual}")
        
        if invalid_lines:
            line_names = ', '.join(invalid_lines)
            _logger.warning(f"Líneas inválidas detectadas: {line_names}")
            raise ValidationError(_("Las siguientes líneas no tienen montos pendientes disponibles:\n\n%s") % line_names)
        
        # Agregar las líneas válidas al agrupador
        if valid_lines:
            _logger.info(f"Agregando {len(valid_lines)} líneas de crédito de {len(selected_invoices)} facturas al agrupador")
            
            # Agregar las líneas de crédito al agrupador
            self.payment_aggregator_id.mps_credits_line_ids = [(4, line.id) for line in valid_lines]
            
            # Crear registros de agregador para las nuevas líneas
            self.payment_aggregator_id.set_account_move_line(valid_lines)
            
            _logger.info(f"Facturas agregadas exitosamente: {selected_invoices.mapped('name')}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _("Se agregaron %d facturas (%d líneas de crédito) al agrupador de pagos.") % (len(selected_invoices), len(valid_lines)),
                    'type': 'success',
                    'sticky': False,
                }
            }
        
        return {'type': 'ir.actions.act_window_close'}

    def action_debug(self):
        """
        Método de debug para investigar el problema.
        """
        self.ensure_one()
        
        _logger.info("=== DEBUG WIZARD ===")
        _logger.info(f"Payment Aggregator ID: {self.payment_aggregator_id.id}")
        _logger.info(f"Partner ID: {self.partner_id.id}")
        _logger.info(f"Currency ID: {self.currency_id.id}")
        _logger.info(f"Partner Type: {self.partner_type}")
        _logger.info(f"Move IDs count: {len(self.move_ids)}")
        _logger.info(f"Move IDs: {self.move_ids.mapped('name')}")
        _logger.info(f"Move Line IDs count: {len(self.move_line_ids)}")
        _logger.info(f"Move Line IDs: {self.move_line_ids.mapped('display_name')}")
        
        # Verificar el agrupador
        if self.payment_aggregator_id:
            aggregator = self.payment_aggregator_id
            _logger.info(f"Aggregator name: {aggregator.name}")
            _logger.info(f"Aggregator state: {aggregator.state}")
            _logger.info(f"Credits lines count: {len(aggregator.mps_credits_line_ids)}")
            _logger.info(f"Credits lines: {aggregator.mps_credits_line_ids.mapped('display_name')}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Debug Info'),
                'message': _("Revisa los logs para información de debug."),
                'type': 'info',
                'sticky': False,
            }
        }
