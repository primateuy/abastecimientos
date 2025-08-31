from odoo import _, api, fields, models, tools

class ResCurrency(models.Model):

    _inherit = 'res.currency'

    account_journal_id = fields.Many2one(
        'account.journal',
        string='Account Journal',
        domain=lambda self: str(self._getAccountJournalDomain())
    )

    @api.onchange('accout_journal_id')
    def onchange_accout_journal_id(self):
        if self.account_journal_id:
            if self.account_journal_id.intermediate_diary == False:
                self.account_journal_id.intermediate_diary = True

    # Metodo para obtener el domain para los diarios
    def _getAccountJournalDomain(self):
        return ['|',('type','=','cash'),('type','=','bank'),('intermediate_diary','=',True),('company_id','=', self.env.company.id)]