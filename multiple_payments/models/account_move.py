from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_create_payment_aggregators(self):
        """
        Acción para crear agregadores de pagos desde facturas seleccionadas.
        
        Este método se llama desde el server action y abre el wizard
        con las facturas seleccionadas pre-cargadas.
        Valida que las facturas no estén pagadas antes de proceder.
        
        Returns:
            dict: Acción para abrir el wizard o notificación de error
        """
        # Verificar que hay facturas seleccionadas
        if not self:
            raise UserError("Debe seleccionar al menos una factura.")
        
        # Verificar que las facturas no estén pagadas
        paid_invoices = self.filtered(lambda inv: inv.payment_state == 'paid')
        if paid_invoices:
            invoice_names = ', '.join(paid_invoices.mapped('name'))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("No se puede crear agregadores de pago para facturas ya pagadas:\n\n%s") % invoice_names,
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        # Verificar que las facturas tengan líneas de crédito disponibles
        invoices_without_credit = []
        for invoice in self:
            credit_lines = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable'] and not l.reconciled
            )
            if not credit_lines:
                invoices_without_credit.append(invoice.name)
        
        if invoices_without_credit:
            invoice_names = ', '.join(invoices_without_credit)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("Las siguientes facturas no tienen líneas de crédito disponibles:\n\n%s") % invoice_names,
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        # Abrir el wizard con las facturas seleccionadas
        action = {
            'name': 'Crear agregadores de pago',
            'type': 'ir.actions.act_window',
            'res_model': 'mps.payment.aggregator.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_ids': [(6, 0, self.ids)],
            }
        }
        return action
