
from odoo import models

class AccountMovePatch(models.Model):
    _inherit = "account.move"

    def _register_hook(self):
        res = super()._register_hook()
        origin = self.fields_get

        def patched_fields_get(self, allfields=None, attributes=None):
            res_fields = origin(allfields=allfields, attributes=attributes)
            fld = res_fields.get("invoice_date")
            if fld:
                fld["importable"] = True
                fld["readonly"] = False
            return res_fields

        self._patch_method("fields_get", patched_fields_get)
        return res
