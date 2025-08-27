
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

class PaymentAggregatorLines(models.Model):
    _inherit = 'mps.payment.aggregator'

    def _get_base_journal(self):
        # Intenta el diario explícito del agregador; si no, el mapeo por moneda.
        journal = getattr(self, 'journal_id', False)
        if journal:
            return journal
        cur = getattr(self, 'currency_id', False)
        if cur and getattr(cur, 'account_journal_id', False):
            return cur.account_journal_id
        return False

    def _create_lines_payment_payments(self):
        self.ensure_one()
        payments = self.env['account.payment']
        base_journal = self._get_base_journal()
        if not base_journal:
            raise UserError(_('No se encontró Diario base para crear transferencias.'))

        inbound = getattr(self.receiptbook_id, 'type', 'inbound') == 'inbound'
        lines = getattr(self, 'mps_payment_methods_line_ids', self.env['mps.payment.methods.line'])

        for line in lines:
            dest_journal = getattr(line, 'journal_id', False)
            if not dest_journal:
                # si la línea no define diario, la salteamos
                continue

            # Dirección: inbound -> desde base hacia destino; outbound -> desde destino hacia base
            source_journal = base_journal if inbound else dest_journal
            target_journal = dest_journal if inbound else base_journal

            # Monto en moneda del journal origen
            amount = 0.0
            # Preferimos 'amount' si representa el importe en moneda de diario
            if hasattr(line, 'amount') and line.amount:
                amount = float(line.amount)
            else:
                # fallback por tipo de recibo usando payment_amount * exchange_rate cuando aplica
                pm_amount = float(getattr(line, 'payment_amount', 0.0) or 0.0)
                rate = float(getattr(line, 'exchange_rate', 0.0) or 0.0)
                if inbound:
                    amount = pm_amount * rate if rate else pm_amount
                else:
                    amount = pm_amount if pm_amount else 0.0

            # Moneda del journal origen (o de la compañía si el diario no tiene)
            currency_id = source_journal.currency_id.id or self.company_id.currency_id.id

            pay = self._create_payment_acount(
                is_internal_transfer=True,
                journal_id=source_journal.id,
                destination_journal_id=target_journal.id,
                amount=amount,
                currency_id=currency_id,
                date=getattr(self, 'date', fields.Date.context_today(self)),
                ref=_('Transferencia interna - %s') % (getattr(line, 'display_name', str(line.id))),
            )
            payments |= pay
        return payments
