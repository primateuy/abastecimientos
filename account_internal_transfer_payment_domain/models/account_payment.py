# -*- coding: utf-8 -*-
import logging
from odoo import api, models
from odoo.osv import expression

_logger = logging.getLogger(__name__)

ALLOWED_INBOUND_CODES_INTERNAL = ["manual", "in_third_party_checks", "new_third_party_checks"]
ALLOWED_OUTBOUND_CODES_INTERNAL = ["manual", "out_third_party_checks"]

class AccountPayment(models.Model):
    _inherit = "account.payment"

    # ---------------------------- Helpers ----------------------------------
    def _get_payment_method_line_domain(self):
        """Build the domain for account.payment.method.line considering internal transfers.
        If the parent implementation exists, extend it; otherwise, compose a minimal base.
        """
        try:
            domain = super()._get_payment_method_line_domain()  # type: ignore[attr-defined]
        except Exception:
            # Fallback base
            self.ensure_one()
            if not self.journal_id:
                return []
            domain = [("journal_id", "=", self.journal_id.id)]
            if self.payment_type:
                domain.append(("payment_type", "=", self.payment_type))

        # Extend for internal transfers
        self.ensure_one()
        if self.is_internal_transfer:
            allowed = (
                ALLOWED_INBOUND_CODES_INTERNAL
                if (self.payment_type or "inbound") == "inbound"
                else ALLOWED_OUTBOUND_CODES_INTERNAL
            )
            domain = expression.AND([domain, [("payment_method_id.code", "in", allowed)]])
        return domain

    # ---------------------------- Computes ---------------------------------
    @api.depends("journal_id", "payment_type", "is_internal_transfer")
    def _compute_available_payment_method_line_ids(self):
        """Recompute using our domain so the field-domain [('id','in', available_payment_method_line_ids)]
        includes 'new_third_party_checks' in internal inbound.
        """
        PaymentMethodLine = self.env["account.payment.method.line"]
        for rec in self:
            try:
                domain = rec._get_payment_method_line_domain()
            except Exception as e:
                _logger.debug("Fallback domain due to error in _get_payment_method_line_domain: %s", e)
                domain = []
            rec.available_payment_method_line_ids = PaymentMethodLine.search(domain)