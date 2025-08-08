from odoo import models

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _prepare_invoice(self):
        self.ensure_one()
        vals = super()._prepare_invoice()

        # Detectar el campo Many2one a purchase.order.type sin asumir nombre
        po_type_field = next(
            (name for name, fld in self._fields.items()
             if getattr(fld, 'type', None) == 'many2one'
             and getattr(fld, 'comodel_name', '') == 'purchase.order.type'),
            None
        )
        po_type = getattr(self, po_type_field, False) if po_type_field else False

        if po_type:
            vals['purchase_type_id'] = po_type.id
        return vals