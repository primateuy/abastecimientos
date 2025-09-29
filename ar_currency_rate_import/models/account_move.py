from odoo import api, fields, models

class AccountMove(models.Model):
    _inherit = "account.move"

    # Campo "sombra" para importación. Solo para el wizard de import.
    import_l10n_ar_currency_rate = fields.Float(
        string="(Import) AR Currency Rate",
        help="Usar este campo solo al importar. Se copiará a l10n_ar_currency_rate.",
        digits="Product Price",
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Copiamos el valor importado al campo real si viene en el CSV/XLS
        for vals in vals_list:
            if "import_l10n_ar_currency_rate" in vals:
                rate = vals.pop("import_l10n_ar_currency_rate")
                # Si tu campo real está en este modelo:
                if rate not in (False, None):
                    vals["l10n_ar_currency_rate"] = rate
        moves = super().create(vals_list)
        return moves

    def write(self, vals):
        # Soporta importaciones que usen "Actualizar registros existentes"
        if "import_l10n_ar_currency_rate" in vals:
            rate = vals.pop("import_l10n_ar_currency_rate")
            if rate not in (False, None):
                vals["l10n_ar_currency_rate"] = rate
        return super().write(vals)
