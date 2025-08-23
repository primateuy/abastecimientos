from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    warehouse_ids = fields.Many2many('stock.warehouse', string="Almacenes permitidos")
    
    def action_add_all_warehouses(self):
        for user in self:
            all_warehouses = self.env['stock.warehouse'].search([])
            user.warehouse_ids = [(6, 0, all_warehouses.ids)]