# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    group_id = fields.Many2one('stock.warehouse.group.report', string='Grupo de Almacenes')
    
    @api.model_create_multi
    def create(self, vals_list):
        default_group = self.env.ref('stock_report.stock_warehouse_group_default')
        for vals in vals_list:
            if not vals.get('group_id'):
                vals['group_id'] = default_group.id
        return super().create(vals_list)