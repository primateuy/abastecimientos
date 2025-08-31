from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class AccountJournalAggregator(models.Model):

    _name = 'account.journal.aggregator'
    _description = 'Model to save the intermediate diaries'
    _rec_name="account_journal_id"

    active = fields.Boolean(default=True)
    account_journal_id = fields.Many2one(
        'account.journal',
        string='Account Journal',
        domain=lambda self: "[('company_id','=', %s)]" % self.env.company.id,
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='company',
        default= lambda self: self.env.company.id,
        required=True,
        domain=lambda self: "[('id','in', %s)]" % self.env.user.company_ids.ids,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='currency',
        required=True
    )

    @api.constrains('company_id', 'currency_id')
    def _validate_intermediate_diary(self):
        for record in self:
            if record.company_id and record.currency_id:
                repeated_account_journal = self.search([('company_id', '=', record.company_id.id),('currency_id', '=', record.currency_id.id), ('id', '!=', record.id)], limit=1)
                if repeated_account_journal:
                    raise ValidationError(_('You can have only one intermediate diary per currency in this company'))