
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

class PaymentAggregatorInvoices(models.Model):
    _inherit = 'mps.payment.aggregator'

    def _create_invoices_payment(self):
        """Crea el pago principal (cliente/proveedor) por el total del recibo,
        usando el diario base (self.currency_id.account_journal_id) y el partner del agregador.
        - inbound: partner_type=customer, amount = sum(line.amount)
        - outbound: partner_type=supplier, amount = sum(line.payment_amount)
        """
        self.ensure_one()
        # Base vals del helper del módulo (si existe)
        if hasattr(self, '_get_standard_payment'):
            vals = self._get_standard_payment()
        else:
            vals = {
                'partner_id': getattr(self, 'customer_id', False) and self.customer_id.id or False,
                'date': getattr(self, 'date', False),
                'amount': 0.0,
                'is_internal_transfer': False,
                'payment_type': getattr(self.receiptbook_id, 'type', 'inbound') if getattr(self, 'receiptbook_id', False) else 'inbound',
                'journal_id': getattr(self.receiptbook_id, 'account_journal_id', False) and self.receiptbook_id.account_journal_id.id or False,
                'partner_type': getattr(self.receiptbook_id, 'partner_type', 'customer') if getattr(self, 'receiptbook_id', False) else 'customer',
                'payment_aggregator_id': self.id,
            }

        # Totales según tipo de recibo
        total = 0.0
        lines = getattr(self, 'mps_payment_methods_line_ids', self.env['mps.payment.methods.line'])
        if getattr(self.receiptbook_id, 'type', 'inbound') == 'inbound':
            for l in lines:
                total += (getattr(l, 'amount', 0.0) or 0.0)
        else:
            for l in lines:
                total += (getattr(l, 'payment_amount', 0.0) or 0.0)

        vals.update({
            'amount': total or 0.0,
            'is_internal_transfer': False,
        })

        # Validaciones mínimas
        if not vals.get('journal_id'):
            raise UserError(_('No se encontró un Diario base (currency_id.account_journal_id) para registrar el pago principal.'))
        if not vals.get('partner_id'):
            raise UserError(_('Debe seleccionar un Partner (cliente/proveedor) en el agregador.'))

        # Crear y publicar
        payment = self.create_publish_payment(vals) if hasattr(self, 'create_publish_payment') else self.env['account.payment'].create(vals)
        if not hasattr(self, 'create_publish_payment'):
            payment.action_post()
            if hasattr(payment, 'set_transaction_type'):
                payment.set_transaction_type()
        return payment
