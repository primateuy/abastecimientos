
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

class PaymentAggregatorHelpers(models.Model):
    _inherit = 'mps.payment.aggregator'

    def _create_payment_acount(self, *args, **kwargs):
        """
        Método defensivo para crear un account.payment desde el agregador.
        Acepta kwargs flexibles:
          - journal_id, destination_journal_id, is_internal_transfer, payment_type,
            amount, currency_id, partner_id, date, payment_method_id, ref, partner_type
        Fallbacks sensatos para v16 (NOT NULL partner_type).
        """
        self.ensure_one()
        env = self.env

        # Base: helper del módulo si existe
        if hasattr(self, '_get_standard_payment'):
            vals = dict(self._get_standard_payment() or {})
        else:
            vals = {}

        payment_type = kwargs.get('payment_type')
        if not payment_type:
            # Si hay talonario, usar su tipo; default inbound
            payment_type = getattr(self.receiptbook_id, 'type', 'inbound') if getattr(self, 'receiptbook_id', False) else 'inbound'

        is_internal = bool(kwargs.get('is_internal_transfer', False))

        # journal origen obligatorio
        journal_id = kwargs.get('journal_id')
        if not journal_id:
            # fallback: diario del talonario (correcto para clientes y proveedores)
            journal_id = getattr(self.receiptbook_id, 'account_journal_id', False) and self.receiptbook_id.account_journal_id.id or False
        if not journal_id:
            raise UserError(_('No se encontró Diario para crear el pago.'))

        amount = float(kwargs.get('amount', 0.0))
        if amount is None:
            amount = 0.0

        # currency
        currency_id = kwargs.get('currency_id')
        if not currency_id:
            currency_id = getattr(self.currency_id, 'id', False) or getattr(self.company_id.currency_id, 'id', False)

        # partner & tipo
        partner_id = kwargs.get('partner_id')
        # si es interna, sin partner
        if is_internal:
            partner_id = False
            partner_type = 'supplier'  # NOT NULL constraint workaround
        else:
            # intentar tomar del agregador si no viene
            if not partner_id:
                partner_id = getattr(self, 'customer_id', False) and self.customer_id.id or getattr(self, 'partner_id', False) and self.partner_id.id or False
            # partner_type explícito o derivado
            partner_type = kwargs.get('partner_type')
            if not partner_type:
                partner_type = 'customer' if payment_type == 'inbound' else 'supplier'

        vals.update({
            'journal_id': journal_id,
            'is_internal_transfer': is_internal,
            'payment_type': payment_type,
            'amount': amount,
            'currency_id': currency_id,
            'partner_id': partner_id,
            'partner_type': partner_type,
            'date': kwargs.get('date') or getattr(self, 'date', False),
            'payment_method_id': kwargs.get('payment_method_id'),
            'ref': kwargs.get('ref') or _('Internal Transfer') if is_internal else _('Aggregated Payment'),
            'payment_aggregator_id': self.id,
        })

        if is_internal:
            dest = kwargs.get('destination_journal_id')
            if not dest:
                dest = getattr(self, 'destination_journal_id', False) and self.destination_journal_id.id or False
            if not dest:
                raise UserError(_('Falta destination_journal_id para la transferencia interna.'))
            vals['destination_journal_id'] = dest

        # Crear y postear
        if hasattr(self, 'create_publish_payment'):
            payment = self.create_publish_payment(vals)
        else:
            payment = env['account.payment'].create(vals)
            payment.action_post()
            if hasattr(payment, 'set_transaction_type'):
                payment.set_transaction_type()
        return payment

    # Alias comunes por si el código llama a los nombres "correctamente" escritos
    def _create_payment_account(self, *args, **kwargs):
        return self._create_payment_acount(*args, **kwargs)

    def _create_payment(self, *args, **kwargs):
        return self._create_payment_acount(*args, **kwargs)
