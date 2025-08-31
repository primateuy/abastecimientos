from odoo import models

class AccountMove(models.Model):
    _inherit = "account.move"

    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        fld = res.get("invoice_date")
        if fld:
            # fuerza a que aparezca en el asistente de importación
            fld["importable"] = True
        return res
