from odoo import models, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        fld = res.get("invoice_date")
        if fld:
            # forzar que aparezca en el asistente de importación
            fld["importable"] = True
            # y asegurarnos que el wizard no lo esconda por readonly
            fld["readonly"] = False
        return res

    @api.model_create_multi
    def create(self, vals_list):
        # Bloquear seteo de invoice_date si el diario usa CFE
        for vals in vals_list:
            if "invoice_date" in vals:
                journal_id = vals.get("journal_id") or self.env.context.get("default_journal_id")
                if journal_id:
                    jr = self.env["account.journal"].browse(journal_id)
                    try:
                        if getattr(jr, "diario_cfe", False):
                            raise UserError(_("No se puede establecer la Fecha de factura cuando el diario utiliza CFE."))
                    except Exception:
                        # si el campo no existe no bloqueamos
                        pass
        return super().create(vals_list)

    def write(self, vals):
        # Bloquear modificación si el diario usa CFE
        if "invoice_date" in vals:
            with_cfe = self.filtered(lambda m: getattr(m.journal_id, "diario_cfe", False))
            if with_cfe:
                raise UserError(_("No se puede modificar la Fecha de factura en diarios con CFE."))
        return super().write(vals)
