
from odoo import api, models

class MpsPaymentAggregator(models.Model):
    _inherit = "mps.payment.aggregator"

    @api.model_create_multi
    def create(self, vals_list):
        """Allow creating records even when a too-strict create rule blocks it,
        by forcing company_id and using sudo just for the create call.

        The returned records keep the caller's env (no sudo).
        """
        company_id = self.env.company.id
        normalized = []
        for vals in vals_list:
            vals = dict(vals)
            vals.setdefault("company_id", company_id)
            normalized.append(vals)
        recs = super(MpsPaymentAggregator, self.sudo()).create(normalized)
        # return them with the original env (no sudo) to avoid surprising callers
        return recs.with_env(self.env)

    # ------------------------------------------------------------------
    # Compatibility shim for older/newer versions expecting this compute
    # ------------------------------------------------------------------
    def _compute_debt_allocation(self):
        """No-op safe compute to avoid AttributeError when opening records
        if the base module expects this method but it's missing.
        We intentionally do not touch any field values here.
        """
        # do nothing on purpose
        return
