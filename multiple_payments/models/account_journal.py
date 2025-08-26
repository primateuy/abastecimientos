from odoo import _, api, fields, models

class AccountJournal(models.Model):

    _inherit = 'account.journal'

    intermediate_diary = fields.Boolean(default=False)