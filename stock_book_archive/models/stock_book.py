# -*- coding: utf-8 -*-
from odoo import fields, models


class StockBook(models.Model):
    _inherit = "stock.book"

    # Standard Odoo archiving mechanism: when a model has an `active` boolean field,
    # the UI automatically provides Archive / Unarchive actions and an "Archived" filter.
    active = fields.Boolean(default=True, index=True)
