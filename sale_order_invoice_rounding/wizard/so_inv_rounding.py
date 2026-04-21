# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleInvoiceRounding(models.TransientModel):
    _name = 'custom.so.inv.rounding'
    
    rounding_value = fields.Float(
        'Rounding Off Value',
        required=True,
    )
    
    def action_rounding_amount(self):
        self.ensure_one()
        if self._context.get('active_model') == 'sale.order':
            sale_id = self.env[self._context.get('active_model')].browse(self._context.get('active_id'))
            rounding_product_id = sale_id.company_id.custom_rounding_product_id
            sale_id.write({
                'order_line': [(0, 0, {
                    'product_id': rounding_product_id.id,
                    'product_uom_qty': 1,
                    'price_unit': self.rounding_value,
                })],
            })
        elif self._context.get('active_model') == 'account.move':
            invoice_id = self.env[self._context.get('active_model')].browse(self._context.get('active_id'))
            rounding_product_id = invoice_id.company_id.custom_rounding_product_id
            invoice_id.write({
                'invoice_line_ids': [(0, 0, {
                    'product_id': rounding_product_id.id,
                    'quantity': 1,
                    'price_unit': self.rounding_value,
                })],
            })
        return True

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
