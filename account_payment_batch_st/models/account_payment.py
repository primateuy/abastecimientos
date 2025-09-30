# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields,  api, _


class AccountPayment(models.Model):
    _inherit = "account.payment"

    batch_payment_st_id = fields.Many2one('account.payment.batch.st', string="Lote")
    amount_signed = fields.Monetary(
        currency_field='currency_id', compute='_compute_amount_signed',
        help='Negative value of amount field if payment_type is outbound')
    payment_method_name = fields.Char(related='payment_method_line_id.name')

    @api.depends('amount', 'payment_type')
    def _compute_amount_signed(self):
        for payment in self:
            if payment.payment_type == 'outbound':
                payment.amount_signed = -payment.amount
            else:
                payment.amount_signed = payment.amount

    @api.model
    def create_batch_payment(self):
        # We use self[0] to create the batch; the constrains on the model ensure
        # the consistency of the generated data (same journal, same payment method, ...)
        batch = self.env['account.payment.batch.st'].create({
            # 'journal_id': self[0].journal_id.id,
            'payment_ids': [(4, payment.id, None) for payment in self],
            # 'payment_method_id': self[0].payment_method_id.id,
            'batch_type': self[0].payment_type,
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.payment.batch.st",
            "views": [[False, "form"]],
            "res_id": batch.id,
        }

    def _ensure_batch(self):
        batch_id = self.mapped('batch_payment_st_id')[:1]
        is_internal_transfer_menu = self.env.context.get('is_internal_transfer_menu', False)
        # is_internal_transfer_menu es True es una transf interna y NO queremos un batch
        if not batch_id and not is_internal_transfer_menu:
            batch_id = self.env['account.payment.batch.st'].create({
                'batch_type': self.payment_type,
                'partner_type': self.partner_type,
                'company_id': self.company_id.id,

            })
        return batch_id

    def add_to_payment_batch(self):
        batch_id = self._ensure_batch()
        self.batch_payment_st_id = batch_id.id
        self.batch_payment_st_id = self._ensure_batch().id
        return {
                    'name': _("Batch Payment"),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.payment.batch.st',
                    'context': {'create': False},
                    'view_mode': 'form',
                    'res_id': batch_id.id,
                }

    def action_post(self):
        # import pdb; pdb.set_trace()
        compania_actual = self.env.company
        if compania_actual.usa_grupo_pago:
            self.batch_payment_st_id = self._ensure_batch().id
        # import pdb; pdb.set_trace()
        res = super().action_post()
        if compania_actual.usa_grupo_pago:
            if len(self.mapped('batch_payment_st_id')) == 1:
                return {
                    'name': _("Batch Payment"),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.payment.batch.st',
                    'context': {'create': False},
                    'view_mode': 'form',
                    'res_id': self.mapped('batch_payment_st_id').id,
                }
        return res

    def action_post_and_new(self):
        self.ensure_one()
        res = super().action_post_and_new()        
        if self.env.user.company_id.usa_grupo_pago:
            res['context'].update({'default_batch_payment_st_id': self.batch_payment_st_id.id})
        # import pdb; pdb.set_trace()
        return res

    def button_open_batch_payment_st(self):
        ''' Redirect the user to the batch payments containing this payment.
        :return:    An action on account.payment.batch.st.
        '''
        self.ensure_one()

        return {
            'name': _("Batch Payment"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.batch.st',
            'context': {'create': False},
            'view_mode': 'form',
            'res_id': self.batch_payment_st_id.id,
        }

    def _is_latam_check_payment(self, check_subtype=False):
            return self.payment_method_code in ['in_third_party_checks', 'out_third_party_checks', 'return_third_party_checks', 'new_third_party_checks', 'own_checks']