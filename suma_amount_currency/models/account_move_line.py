from odoo import api, models, fields

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"
    
    amount_currency = fields.Monetary(
        string="Amount in Currency",
        store=True,
        currency_field="currency_id",
        group_operator="sum",   # 👈 fuerza el comportamiento nativo de suma
    )

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """
        Suma 'amount_currency' sólo si el grupo tiene 1 sola divisa.
        Si groupby incluye 'currency_id', no alteramos (siempre suma).
        Se aplica SIEMPRE (sin depender del contexto) para account.move.line.
        """
        res = super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

        # ¿La vista pidió agregar amount_currency?
        wants_amount_currency = any(f.split(":")[0] == "amount_currency" for f in fields)
        if not wants_amount_currency:
            return res

        groupby_fields = [gb.split(":")[0] for gb in (groupby or [])]
        # Si agrupás por divisa, ya es homogéneo -> dejá el sum nativo
        if "currency_id" in groupby_fields:
            return res

        for row in res:
            row_domain = row.get("__domain", domain)
            currency_groups = super(AccountMoveLine, self).read_group(
                row_domain, ["currency_id"], ["currency_id"]
            )
            if len(currency_groups) == 1:
                sum_row = super(AccountMoveLine, self).read_group(
                    row_domain, ["amount_currency:sum"], []
                )
                safe_sum = sum_row and sum_row[0].get("amount_currency_sum")
                if "amount_currency" in row:
                    row["amount_currency"] = safe_sum or 0.0
                else:
                    row["amount_currency_sum"] = safe_sum or 0.0
            else:
                # 🔧 clave: devolver un número, no None
                if "amount_currency" in row:
                    row["amount_currency"] = 0.0
                else:
                    row["amount_currency_sum"] = 0.0

        return res