from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountMoveAggregator(models.Model):
    """
    Extensión del modelo account.move para funcionalidad del agrupador de pagos.
    """
    _inherit = 'account.move'

    def action_add_to_aggregator(self):
        """
        Agrega las facturas seleccionadas al agrupador de pagos.
        Este método se llama desde el listado de facturas.
        """
        self.ensure_one()
        
        # Obtener el wizard_id del contexto
        wizard_id = self.env.context.get('wizard_id')
        if not wizard_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("No se encontró el wizard del agrupador."),
                    'type': 'error',
                    'sticky': False,
                }
            }
        
        # Obtener el wizard
        wizard = self.env['mps.payment.aggregator.add.invoices.wizard'].browse(wizard_id)
        if not wizard.exists():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("El wizard del agrupador no existe."),
                    'type': 'error',
                    'sticky': False,
                }
            }
        
        # Llamar al método del wizard para agregar las facturas
        return wizard.action_add_selected_invoices(self.ids)

    def action_add_multiple_to_aggregator(self):
        """
        Agrega múltiples facturas seleccionadas al agrupador de pagos.
        Este método se llama desde el listado de facturas con selección múltiple.
        """
        if not self:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _("No se seleccionaron facturas."),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Obtener el wizard_id del contexto
        wizard_id = self.env.context.get('wizard_id')
        if not wizard_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("No se encontró el wizard del agrupador."),
                    'type': 'error',
                    'sticky': False,
                }
            }
        
        # Obtener el wizard
        wizard = self.env['mps.payment.aggregator.add.invoices.wizard'].browse(wizard_id)
        if not wizard.exists():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _("El wizard del agrupador no existe."),
                    'type': 'error',
                    'sticky': False,
                }
            }
        
        # Llamar al método del wizard para agregar las facturas
        return wizard.action_add_selected_invoices(self.ids)
