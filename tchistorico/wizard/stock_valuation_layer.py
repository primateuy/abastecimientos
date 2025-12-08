from odoo import models, api, _
from odoo.exceptions import UserError


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    def compute_secondary_amount(self):
        if self._context.get('active_model') == 'stock.valuation.layer':
            domain = [('id', 'in', self._context.get('active_ids', []))]
        else:
            raise UserError('Esta operación debe realizarse desde el menu Apuntes Contables')

        valuations = self.env['stock.valuation.layer'].search(domain)
        if not valuations:
            raise UserError(_('No se encontaron apuntes'))
        valuations.compute_remaining_value()