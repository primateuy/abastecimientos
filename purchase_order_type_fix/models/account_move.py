from odoo import api, fields, models

class AccountMove(models.Model):
    _inherit = 'account.move'

    purchase_type_id = fields.Many2one(
        'purchase.order.type',
        string='Purchase Type',
        compute="_compute_purchase_type_id",
        store=True,
        readonly=False,
        precompute=True,
        copy=True,
    )

    @api.depends('partner_id', 'company_id', 'move_type')
    def _compute_purchase_type_id(self):
        Type = self.env['purchase.order.type']
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                move.purchase_type_id = False
                continue
            # Si viene de la OC vía _prepare_invoice, respetarlo
            if move.purchase_type_id:
                continue
            t = False
            if move.partner_id:
                t = (move.partner_id.with_company(move.company_id).purchase_type or
                     move.partner_id.commercial_partner_id.with_company(move.company_id).purchase_type)
            if not t:
                t = Type.search([('company_id', 'in', [move.company_id.id, False])], limit=1)
            move.purchase_type_id = t

    @api.depends('purchase_type_id', 'move_type', 'company_id')
    def _compute_journal_id(self):
        super()._compute_journal_id()
        for move in self.filtered(lambda m: m.move_type in ('in_invoice', 'in_refund') and m.purchase_type_id.journal_id):
            move.journal_id = move.purchase_type_id.journal_id

    @api.onchange('purchase_type_id')
    def _onchange_purchase_type_id_set_journal(self):
        if self.move_type in ('in_invoice', 'in_refund') and self.purchase_type_id.journal_id:
            self.journal_id = self.purchase_type_id.journal_id