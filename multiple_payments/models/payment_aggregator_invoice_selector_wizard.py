# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
import logging

_logger = logging.getLogger(__name__)


class MPSPaymentAggregatorInvoiceSelectorWizard(models.TransientModel):
    """
    Wizard para seleccionar facturas y agregarlas al agrupador de pagos.
    Funciona como un many2many con filtros aplicados.
    """
    _name = 'mps.payment.aggregator.invoice.selector.wizard'
    _description = 'Wizard para seleccionar facturas del agrupador'

    # Campos del agrupador
    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='Agrupador de Pagos',
        required=True,
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente/Proveedor',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        readonly=True
    )
    partner_type = fields.Selection(
        [('customer', 'Cliente'), ('supplier', 'Proveedor')],
        string='Tipo de Partner',
        readonly=True
    )

    # Campo principal para selección
    invoice_ids = fields.Many2many(
        'account.move',
        string='Facturas Disponibles',
        help='Seleccione las facturas que desea agregar al agrupador',
        domain='_get_invoice_domain'
    )
    
    # Campo para el dominio de facturas
    invoice_domain = fields.Binary(
        string='Dominio de Facturas',
        compute='_compute_invoice_domain',
        store=False
    )

    @api.model
    def default_get(self, fields_list):
        """
        Inicializa los valores por defecto del wizard.
        Obtiene los datos del agrupador y filtra las facturas disponibles.
        """
        res = super().default_get(fields_list)
        
        # Obtener el ID del agrupador desde el contexto
        active_id = self.env.context.get('active_id')
        if not active_id:
            return res
            
        aggregator = self.env['mps.payment.aggregator'].browse(active_id)
        if not aggregator.exists():
            return res
        
        _logger.info(f"=== INICIALIZANDO WIZARD PARA AGRUPADOR {aggregator.name} ===")
        
        # Configurar campos del agrupador
        res['payment_aggregator_id'] = aggregator.id
        res['partner_id'] = aggregator.customer_id.id
        res['currency_id'] = aggregator.currency_id.id
        res['partner_type'] = aggregator.receiptbook_id.partner_type if aggregator.receiptbook_id else 'customer'
        
        _logger.info(f"Wizard inicializado para agrupador: {aggregator.name}")
        
        return res

    @api.depends('payment_aggregator_id')
    def _compute_invoice_domain(self):
        """
        Calcula el dominio para las facturas disponibles.
        """
        for record in self:
            domain = record._get_invoice_domain()
            record.invoice_domain = domain

    def _get_invoice_domain(self):
        """
        Obtiene el dominio para filtrar las facturas disponibles.
        """
        if not self.payment_aggregator_id:
            return [('id', '=', False)]  # No mostrar ninguna factura si no hay agrupador
        
        # Obtener las facturas disponibles
        available_invoices = self._get_available_invoices(self.payment_aggregator_id)
        
        # Crear dominio que solo incluya las facturas disponibles
        if available_invoices:
            domain = [('id', 'in', available_invoices.ids)]
        else:
            domain = [('id', '=', False)]  # No mostrar ninguna factura si no hay disponibles
        
        _logger.info(f"Dominio de facturas: {domain}")
        return domain

    def _get_available_invoices(self, aggregator):
        """
        Obtiene las facturas disponibles para agregar al agrupador.
        Aplica todos los filtros necesarios: assign_domain + cuentas del diario.
        
        Args:
            aggregator: Recordset del agrupador de pagos
            
        Returns:
            Recordset de facturas disponibles
        """
        _logger.info(f"=== FILTRANDO FACTURAS PARA AGRUPADOR {aggregator.name} ===")
        
        # 1. Usar el domain del agrupador para obtener líneas de crédito
        domain = aggregator.assign_domain()
        _logger.info(f"Domain del agrupador: {domain}")
        
        credit_lines = self.env['account.move.line'].search(domain)
        _logger.info(f"Líneas de crédito encontradas: {len(credit_lines)}")
        
        # 2. Filtrar por cuentas del diario del talonario (solo si están configuradas)
        journal_accounts = self._get_journal_accounts(aggregator)
        if journal_accounts:
            credit_lines = credit_lines.filtered(lambda l: l.account_id.id in journal_accounts)
            _logger.info(f"Líneas después de filtrar por cuentas del diario: {len(credit_lines)}")
        else:
            _logger.info("No se aplicará filtro por cuentas del diario - usando todas las líneas de crédito")
        
        # 3. Excluir líneas ya agregadas al agrupador
        existing_line_ids = aggregator.mps_credits_line_ids.ids
        available_lines = credit_lines.filtered(lambda l: l.id not in existing_line_ids)
        _logger.info(f"Líneas disponibles (excluyendo ya agregadas): {len(available_lines)}")
        
        # 4. Obtener facturas únicas de las líneas disponibles
        available_invoices = available_lines.mapped('move_id')
        _logger.info(f"Facturas encontradas: {len(available_invoices)}")
        
        # 5. Filtrar adicionalmente para asegurar que solo sean facturas (no pagos ni asientos de cambio)
        # Los tipos de factura válidos son: out_invoice, out_refund, in_invoice, in_refund
        valid_move_types = ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']
        available_invoices = available_invoices.filtered(
            lambda inv: inv.move_type in valid_move_types
        )
        _logger.info(f"Facturas válidas (solo facturas, no pagos ni asientos): {len(available_invoices)}")
        
        if available_invoices:
            _logger.info(f"Primeras 5 facturas: {available_invoices[:5].mapped('name')}")
        
        return available_invoices

    def _get_journal_accounts(self, aggregator):
        """
        Obtiene las cuentas configuradas en el diario del talonario para la moneda.
        
        Args:
            aggregator: Recordset del agrupador de pagos
            
        Returns:
            Lista de IDs de cuentas
        """
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
        
        # Si no se encontraron cuentas específicas del diario, no aplicar filtro por cuentas
        if not journal_accounts:
            _logger.info("No se encontraron cuentas del diario, no se aplicará filtro por cuentas")
            return []
        
        return journal_accounts

    def action_add_invoices(self):
        """
        Agrega las facturas seleccionadas al agrupador de pagos.
        Convierte las facturas seleccionadas en líneas de crédito y las agrega.
        """
        self.ensure_one()
        
        if not self.invoice_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _('No se han seleccionado facturas para agregar.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        _logger.info(f"=== AGREGANDO {len(self.invoice_ids)} FACTURAS AL AGRUPADOR ===")
        
        # Obtener las líneas de crédito de las facturas seleccionadas
        selected_invoices = self.invoice_ids
        
        # Filtrar adicionalmente para asegurar que solo sean facturas (no pagos ni asientos de cambio)
        valid_move_types = ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']
        selected_invoices = selected_invoices.filtered(
            lambda inv: inv.move_type in valid_move_types
        )
        
        _logger.info(f"Facturas seleccionadas (solo facturas válidas): {selected_invoices.mapped('name')}")
        
        if not selected_invoices:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _('No se seleccionaron facturas válidas. Solo se permiten facturas, no pagos ni asientos de cambio.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Buscar las líneas de crédito de estas facturas que cumplan los criterios
        domain = self.payment_aggregator_id.assign_domain()
        journal_accounts = self._get_journal_accounts(self.payment_aggregator_id)
        
        # Filtrar por las facturas seleccionadas
        domain.append(('move_id', 'in', selected_invoices.ids))
        
        credit_lines = self.env['account.move.line'].search(domain)
        _logger.info(f"Líneas de crédito encontradas para las facturas seleccionadas: {len(credit_lines)}")
        
        # Filtrar por cuentas del diario si están configuradas
        if journal_accounts:
            credit_lines = credit_lines.filtered(lambda l: l.account_id.id in journal_accounts)
            _logger.info(f"Líneas después de filtrar por cuentas del diario: {len(credit_lines)}")
        else:
            _logger.info("No se aplicará filtro por cuentas del diario - usando todas las líneas de crédito")
        
        # Excluir líneas ya agregadas
        existing_line_ids = self.payment_aggregator_id.mps_credits_line_ids.ids
        new_lines = credit_lines.filtered(lambda l: l.id not in existing_line_ids)
        _logger.info(f"Líneas nuevas para agregar: {len(new_lines)}")
        
        if not new_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Información'),
                    'message': _('No se encontraron líneas de crédito válidas para agregar.'),
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        # Agregar las líneas al agrupador
        self.payment_aggregator_id.mps_credits_line_ids = [(4, line_id) for line_id in new_lines.ids]
        
        _logger.info(f"Líneas agregadas exitosamente: {len(new_lines)}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _("Se agregaron %d facturas (%d líneas de crédito) al agrupador de pagos.") % (len(selected_invoices), len(new_lines)),
                'type': 'success',
                'sticky': False,
            }
        }
