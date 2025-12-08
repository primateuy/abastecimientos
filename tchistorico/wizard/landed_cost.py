from odoo import models, _
from odoo.exceptions import UserError


class LandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    def compute_landed_cost_mr(self):
        if self._context.get('active_model') == 'stock.landed.cost':
            domain = [('id', 'in', self._context.get('active_ids', []))]
        else:
            raise UserError('Esta operación debe realizarse desde el menu Costos en destino')

        landed_cost = self.env['stock.landed.cost'].search(domain)
        if not landed_cost:
            raise UserError(_('No se encontaron apuntes'))
        landed_cost.compute_remaining_value()


