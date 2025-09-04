from odoo import _, api, fields, models
import logging
_logger = logging.getLogger(__name__)

class accountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    total_import = fields.Monetary(
        string='Total Import', store=True,
        currency_field='currency_id',
    )

    payment_aggregator_id = fields.Many2one(
        'mps.payment.aggregator',
        string='payment_aggregator',
    )
    
    # Campos para reconciliación parcial (compatible con sr_partial_invoice_payment)
    partial_matching_number = fields.Char(
        string="Partial Matching Number",
        copy=False,
        index='btree',
        help="Number used to group related lines for partial reconciliation"
    )
    
    sr_is_partial = fields.Boolean(
        string="Sr Is Partial",
        default=False,
        help="Marks this line as part of a partial reconciliation"
    )
    
    @api.model
    def get_next_partial_matching_number(self):
        """
        Obtiene el siguiente número de coincidencia parcial
        Similar al método del módulo sr_partial_invoice_payment
        """
        try:
            sequence = self.env['ir.sequence'].search([
                ('code', '=', 'partial.matching.sequence')
            ])
            if sequence:
                return sequence.next_by_id()
            else:
                # Fallback si no existe la secuencia
                db_name = self.env.cr.dbname[-4:]
                return f"PM{db_name}{self.env.uid}"
        except Exception as e:
            _logger.warning(f"Error obteniendo número de coincidencia parcial: {e}")
            db_name = self.env.cr.dbname[-4:]
            return f"PM{db_name}{self.env.uid}"