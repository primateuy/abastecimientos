from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    account_journal_id = fields.Many2one(
        'account.journal',
        string='Account Journal',
        company_dependent=True,   # ← guarda un valor por compañía (ir.property)
        check_company=True,       # ← valida que el diario sea de la misma compañía del contexto
        help="Journal to use for this currency inrec.company_id the current company."
    )

    @api.onchange('account_journal_id')
    def _onchange_account_journal_id(self):
        """Si seleccionan un diario que no es intermedio, lo marcamos como intermedio.
        Ojo: si no querés modificar el diario acá, reemplazá esto por una constraint."""
        for rec in self:
            journal = rec.account_journal_id
            if journal and not journal.intermediate_diary:
                # Si puede cruzar reglas multi-empresa, considera journal.sudo() y/o un constraint en lugar del onchange.
                journal.intermediate_diary = True
    
    @api.constrains('account_journal_id')
    def _check_account_journal_company(self):
        """Validar contra la compañía activa del entorno, no contra rec.company_id."""
        for rec in self:
            j = rec.account_journal_id
            if not j:
                continue
            current_company = self.env.company
            # Si el diario está ligado a una empresa distinta a la actual, no sirve para este valor company_dependent
            if j.company_id and j.company_id != current_company:
                raise ValidationError(_(
                    "El diario seleccionado (%s) pertenece a %s, pero estás configurando la moneda para %s. "
                    "Cambiá de compañía o elegí un diario de la compañía actual."
                ) % (j.display_name, j.company_id.display_name, current_company.display_name))
            if not j.intermediate_diary:
                raise ValidationError(_(
                    "El diario seleccionado (%s) debe tener habilitado 'intermediate_diary'."
                ) % j.display_name)