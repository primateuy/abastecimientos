# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class Company(models.Model):
    _inherit = 'res.company'

    usa_grupo_pago = fields.Boolean("Usa grupo de pago")