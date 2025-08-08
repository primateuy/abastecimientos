from odoo import fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    purchase_type = fields.Many2one(
        'purchase.order.type',
        string='Default Purchase Type',
        domain="['|', ('company_id','=', False), ('company_id','in', allowed_company_ids)]",
    )
