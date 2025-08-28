
from odoo import _, api, fields, models

class PaymentAggregatorButtons(models.Model):
    _inherit = 'mps.payment.aggregator'

    # === Botones exigidos por la vista ===
    def button_open_accounting_notes(self):
        self.ensure_one()
        return True

    def button_open_grouped_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pagos Agrupados'),
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('payment_aggregator_id', '=', self.id)],
            'context': {'group_by': ['transaction_type']},
        }

    def button_update_accounting_notes(self):
        self.ensure_one()
        return True

    def button_delete_accounting_notes(self):
        self.ensure_one()
        return True

    def button_apply_fifo(self):
        self.ensure_one()
        return True

    def button_assign_all(self):
        self.ensure_one()
        return True

    # === Privados legacy ===
    def _delete_accounting_notes(self):
        self.ensure_one()
        return True

    def _update_accounting_notes(self):
        self.ensure_one()
        return True

    def _open_accounting_notes(self):
        self.ensure_one()
        return True
