from odoo import _, api, fields, models
import logging
_logger = logging.getLogger(__name__)

class accountMoveLinePaymentAggregator(models.Model):
    """
    Modelo para manejar las líneas contables en el agrupador de pagos.
    
    Este modelo mantiene una referencia a las líneas contables originales sin crear
    nuevas líneas contables, evitando así problemas con fechas de bloqueo de impuestos.
    """
    _name = 'account.move.line.payment.aggregator'
    _description = 'Líneas contables del agrupador de pagos'
    
    # Relación con la línea contable original (sin herencia para evitar crear nuevas líneas)
    account_move_line_id = fields.Many2one(
        'account.move.line',
        string='Línea Contable',
        required=True,
        ondelete='cascade'
    )
    
    # Relación con el agrupador de pagos
    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='Agrupador de Pagos',
        required=True,
        ondelete='cascade'
    )
    
    # Campos calculados que obtienen información de la línea contable original
    move_id = fields.Many2one(
        related='account_move_line_id.move_id',
        string='Asiento Contable',
        store=True
    )
    
    currency_id = fields.Many2one(
        related='account_move_line_id.currency_id',
        string='Moneda',
        store=True
    )
    
    amount_currency = fields.Monetary(
        related='account_move_line_id.amount_currency',
        string='Importe en Moneda',
        currency_field='currency_id',
        store=True
    )

    amount_residual_currency = fields.Monetary(
        related='account_move_line_id.amount_residual_currency',
        string='Importe Residual en Moneda',
        currency_field='currency_id',
        store=True
    )
    
    # Campos específicos del agrupador de pagos
    payment_aggregator_total_import = fields.Monetary(
        string='Total Import', 
        store=True,
        currency_field='currency_id',
    )
    
    payment_aggregator_amount_currency = fields.Monetary(
        string="Amount",
        currency_field='currency_id',
    )
    
    payment_aggregator_amount_residual = fields.Monetary(
        string="Total Residual Amount",
        currency_field='currency_id',
    )
    
    # Campos adicionales para facilitar el trabajo con las líneas contables
    partner_id = fields.Many2one(
        related='account_move_line_id.partner_id',
        string='Cliente/Proveedor',
        store=True
    )
    
    account_id = fields.Many2one(
        related='account_move_line_id.account_id',
        string='Cuenta',
        store=True
    )
    
    date = fields.Date(
        related='account_move_line_id.date',
        string='Fecha',
        store=True
    )
    
    date_maturity = fields.Date(
        related='account_move_line_id.date_maturity',
        string='Fecha de Vencimiento',
        store=True
    )
    
    # Campo name para compatibilidad con vistas
    name = fields.Char(
        related='account_move_line_id.name',
        string='Descripción',
        store=True
    )
    
    # Campos adicionales para compatibilidad con vistas
    company_currency_id = fields.Many2one(
        related='account_move_line_id.company_currency_id',
        string='Moneda de la Empresa',
        store=True
    )
    
    move_type = fields.Selection(
        related='account_move_line_id.move_id.move_type',
        string='Tipo de Asiento',
        store=True
    )
    
    @api.model
    def create(self, vals):
        """
        Sobrescribe el método create para evitar problemas con fechas de bloqueo.
        
        Este método no crea nuevas líneas contables, solo registros de referencia.
        """
        _logger.info(f"Creando account.move.line.payment.aggregator con datos: {vals}")
        
        # Asegurar que tenemos la línea contable original
        if 'account_move_line_id' not in vals or not vals['account_move_line_id']:
            _logger.error(f"account_move_line_id faltante o inválido en vals: {vals}")
            raise ValueError("Se requiere account_move_line_id para crear el registro")
        
        # Obtener la línea contable original
        account_move_line = self.env['account.move.line'].browse(vals['account_move_line_id'])
        
        # Validar que la línea contable existe
        if not account_move_line.exists():
            _logger.error(f"Línea contable {vals['account_move_line_id']} no existe")
            raise ValueError(f"La línea contable {vals['account_move_line_id']} no existe")
        
        # Copiar los valores de la línea original si no se proporcionan
        if 'payment_aggregator_amount_currency' not in vals:
            vals['payment_aggregator_amount_currency'] = account_move_line.amount_currency
        
        if 'payment_aggregator_amount_residual' not in vals:
            vals['payment_aggregator_amount_residual'] = account_move_line.amount_residual_currency
            
        _logger.info(f"Creando registro con datos finales: {vals}")
        return super().create(vals)