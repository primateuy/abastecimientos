from odoo import _, api, fields, models, tools
import logging
_logger = logging.getLogger(__name__)


class MPSReceiptBooks(models.Model):

    _name = 'mps.receipt.books'
    _description = 'Model to save the receipt books information'

    def _get_fist_journal(self):
        AccountAccount = self.env['account.journal']
        journal_ids = AccountAccount.search([('type', '=', 'sale')], limit=1)
        return journal_ids

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
    account_journal_id = fields.Many2one('account.journal', string='Journal Payment Account',
                                         default=lambda self: self._get_fist_journal())
    journal_ids_domain = fields.Binary(string="tag domain", help="Dynamic domain used for the account",
                                       compute="_compute_journal_ids_domain")

    @api.depends('partner_type')
    def _compute_journal_ids_domain(self):
        for rep_line in self:
            args = []
            AccountAccount = self.env['account.journal']
            journal_ids = None
            if rep_line.partner_type == 'customer':
                journal_ids = AccountAccount.search([('type', '=', 'sale')])
            elif rep_line.partner_type == 'supplier':
                journal_ids = AccountAccount.search([('type', '=', 'purchase')])
            if journal_ids:
                args = [('id', 'in', journal_ids.ids)]
            rep_line.journal_ids_domain = args

    def create(self, vals):
        # Asignar la compañía actual si no se especificó
        if self.env.company:
            if type(vals) is list:
                for val in vals:
                    val['company_id'] = self.env.company.id
            else:
                vals['company_id'] = self.env.company.id

        
        return super().create(vals)