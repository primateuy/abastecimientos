# -*- coding: utf-8 -*-
from odoo import models, fields

class StockWarehouseGroupReport(models.Model):
    _name = 'stock.warehouse.group.report'
    _description = 'StockWarehouseGroupReport'

    name = fields.Char('Name')
