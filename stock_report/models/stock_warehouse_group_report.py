# -*- coding: utf-8 -*-
from odoo import fields, models


class StockWarehouseGroupReport(models.Model):
	_name = 'stock.warehouse.group.report'
	_description = 'StockWarehouseGroupReport'

	name = fields.Char('Name')
	active = fields.Boolean(default=True)
