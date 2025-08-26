from odoo import _, api, fields, models, tools
import logging
_logger = logging.getLogger(__name__)


class MPSReceiptBooks(models.Model):

    _name = 'mps.receipt.books'
    _description = 'Model to save the receipt books information'

    name = fields.Char(required=True)
    partner_type = fields.Selection([
        ('supplier', 'Supplier'),
        ('customer','Customer')
    ], required=True)
    type = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound','Inbound')
    ], default="outbound")
    enable_reverse_payment = fields.Boolean(default=False)
    # ask_receipt_number = fields.Boolean(default=False)
    reference = fields.Char()
    document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        string='Document Type',
    )
    is_public = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='company',
    )

    def create(self, vals):
        # Asignar la compañía actual si no se especificó
        if self.env.company:
            if type(vals) is list:
                for val in vals:
                    val['company_id'] = self.env.company.id
            else:
                vals['company_id'] = self.env.company.id

        
        return super().create(vals)