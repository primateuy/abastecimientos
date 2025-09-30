from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AccountPaymentBatchSt(models.Model):
    _name = "account.payment.batch.st"
    _description = "Lote de pagos"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, copy=False, string='Nro')
    date = fields.Date(required=True, copy=False, default=fields.Date.context_today, tracking=True, string='Fecha')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        compute='_compute_company_id',
        store=True,
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Socio',
        compute='_compute_partner_id',
        store=True,
    )
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('supplier', 'Vendor'),
    ], compute='_compute_partner_type',  store=True, required=True)
    payment_ids = fields.One2many('account.payment', 'batch_payment_st_id', string="Pagos", required=True)
    matched_move_line_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_matched_move_line_ids',
    )
    l10n_ar_withholding_ids = fields.One2many(
        'account.move.line', 'move_id', string='Withholdings',
        compute='_compute_l10n_ar_withholding_ids',
        readonly=True
    )

    currency_id = fields.Many2one('res.currency', compute='_compute_currency', store=True, readonly=True)
    company_currency_id = fields.Many2one(
        'res.currency',
        string="Company Currency"
    )
    amount_residual = fields.Monetary(
        currency_field='company_currency_id',
        compute='_compute_from_payment_ids',
        store=True,
    )
    amount_residual_currency = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_from_payment_ids',
        store=True,
    )
    amount = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_from_payment_ids',
        store=True,
        string="Importe",
    )
    payment_total = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_from_payment_ids',
        store=True,
        string="Total pago",
    )

    payment_matched_amount  = fields.Monetary(
            currency_field='currency_id',
            compute='_compute_from_payment_ids',
            store=True,
            string="Total Imputado",
        )

    batch_type = fields.Selection(selection=[('inbound', 'Inbound'), ('outbound', 'Outbound')], required=True, default='inbound', tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Publicado'),
        ('reconciled', 'Conciliado'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], store=True, compute='_compute_state', default='draft', tracking=True, string='Estado')

    def add_payment(self):
        payment_difference = abs(sum(self.matched_move_line_ids.mapped('amount_residual')))
        res = self.matched_move_line_ids.with_context(
            force_payment_pro=True,
            default_move_journal_types=('bank', 'cash'),
            default_to_pay_amount=payment_difference,
            default_partner_type=self.payment_ids[:1].partner_type,
            default_company_id=self.payment_ids[:1].company_id.id,
            default_partner_id=self.partner_id.id).action_register_payment()
        res['context'].update({'default_batch_payment_st_id': self.id})
        return res

    @api.depends('payment_ids')
    def _compute_matched_move_line_ids(self):
        with_payments = self.filtered('payment_ids')
        for rec in with_payments:
            rec.matched_move_line_ids  = rec.payment_ids.mapped("matched_move_line_ids")
        (self - with_payments).matched_move_line_ids = False

    @api.depends('payment_ids')
    def _compute_l10n_ar_withholding_ids(self):
        for batch in self:
            batch.l10n_ar_withholding_ids = batch.payment_ids.line_ids.filtered(lambda l: l.tax_line_id.l10n_ar_withholding_payment_type)

    @api.depends('payment_ids')
    def _compute_company_id(self):
        for batch in self:
            batch.company_id = batch.payment_ids[:1].company_id

    @api.depends('payment_ids')
    def _compute_partner_id(self):
        for batch in self:
            batch.partner_id = batch.payment_ids[:1].partner_id

    @api.depends('partner_id')
    def _compute_partner_type(self):
        for batch in self:
            batch.partner_type = batch.payment_ids[:1].partner_type

    @api.depends('payment_ids.state', 'payment_ids.move_id.is_move_sent', 'payment_ids.is_matched')
    def _compute_state(self):
        for batch in self:
            if batch.payment_ids and all(pay.is_matched and pay for pay in batch.payment_ids):
                batch.state = 'reconciled'
            elif batch.payment_ids and all(pay.is_move_sent for pay in batch.payment_ids):
                batch.state = 'sent'
            else:
                states = batch.payment_ids.mapped('state')
                batch.state = states and states[0]

    def mark_as_sent(self):
        self.payment_ids.write({'is_move_sent': True})

    def unmark_as_sent(self):
        self.payment_ids.write({'is_move_sent': False})

    @api.model
    def _create_batch_payment_outbound_sequence(self):
        IrSequence = self.env['ir.sequence']
        if IrSequence.search([('code', '=', 'account.payment.outbound.batch.st')]):
            return
        return IrSequence.sudo().create({
            'name': _("Outbound Batch Payments Sequence"),
            'padding': 8,
            'code': 'account.payment.outbound.batch.st',
            'number_next': 1,
            'number_increment': 1,
            'use_date_range': False,
            'prefix': 'OP-X 0001-',
            #by default, share the sequence for all companies
            'company_id': False,
        })

    @api.model
    def _create_batch_payment_inbound_sequence(self):
        IrSequence = self.env['ir.sequence']
        if IrSequence.search([('code', '=', 'account.payment.inbound.batch.st')]):
            return
        return IrSequence.sudo().create({
            'name': _("Inbound Batch Payments Sequence"),
            'padding': 8,
            'code': 'account.payment.inbound.batch.st',
            'number_next': 1,
            'number_increment': 1,
            'use_date_range': False,
            'prefix': 'RE-X 0001-',
            #by default, share the sequence for all companies
            'company_id': False,
        })

    @api.depends('company_id')
    def _compute_currency(self):
        for batch in self:
            batch.currency_id = batch.company_currency_id or self.env.company.currency_id

    @api.depends('currency_id', 'payment_ids.amount', 'payment_ids.is_matched','payment_ids.state')
    def _compute_from_payment_ids(self):
        for batch in self:
            amount = 0.0
            amount_residual = 0.0
            amount_residual_currency = 0.0
            payment_total = 0.0
            payment_matched_amount = 0.0
            for payment in batch.payment_ids.filtered(lambda x: x.state == 'posted'):
                liquidity_lines, _counterpart_lines, _writeoff_lines = payment._seek_for_lines()
                for line in liquidity_lines:
                    amount += line.currency_id._convert(
                        from_amount=line.amount_currency,
                        to_currency=batch.currency_id,
                        company=line.company_id,
                        date=line.date,
                    )
                    amount_residual += line.amount_residual
                    amount_residual_currency += line.amount_residual_currency
                    payment_total += payment.payment_total
                    payment_matched_amount += line.payment_matched_amount

            batch.amount_residual = amount_residual
            batch.amount = amount
            batch.amount_residual_currency = amount_residual_currency
            batch.payment_total = payment_total
            batch.payment_matched_amount = payment_matched_amount

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        for vals in vals_list:
            vals['name'] = self._get_batch_name(
                vals.get('batch_type'),
                vals.get('date', today),
                vals)
        return super().create(vals_list)

    @api.model
    def _get_batch_name(self, batch_type, sequence_date, vals):
        if not vals.get('name'):
            sequence_code = 'account.payment.inbound.batch.st'
            if batch_type == 'outbound':
                sequence_code = 'account.payment.outbound.batch.st'
            return self.env['ir.sequence'].with_context(sequence_date=sequence_date).next_by_code(sequence_code)
        return vals['name']

    def action_cancel(self):
        for rec in self:
            for payment in rec.payment_ids:
                payment.action_cancel()
            rec.state = 'cancel'

    def action_draft(self):
        for rec in self:
            for payment in rec.payment_ids:
                payment.action_draft()
            rec.state = 'draft'
