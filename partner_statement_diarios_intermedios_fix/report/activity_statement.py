# Copyright 2018 ForgeFlow, S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from collections import defaultdict

from odoo import _, api, models

class ActivityStatement(models.AbstractModel):

    _inherit = "report.partner_statement.activity_statement"
    
    def _get_excluded_journal_ids(self):
        """
        Construye la lista de diarios a excluir:
        - Diario de diferencias de cambio
        - Diarios intermedios pasados por contexto: context['excluded_journal_ids']
          (acepta lista/tupla/set o string CSV)
        - (Opcional) company.intermediate_journal_ids si existe en tu base
        """
        ids_set = set()

        # 1) Diario de diferencias de cambio
        companies = self.env['res.company'].sudo().search([])
        for comp in companies:
            if getattr(comp, "currency_exchange_journal_id", False):
                journal = comp.currency_exchange_journal_id
                if journal:
                    ids_set.add(journal.id)

        # 2) Por contexto (ej: {'excluded_journal_ids': [1,2,3]})
        ctx_val = self.env.context.get("excluded_journal_ids")
        if ctx_val:
            if isinstance(ctx_val, (list, tuple, set)):
                ids_set.update(int(x) for x in ctx_val)
            else:
                # String CSV
                for part in str(ctx_val).split(","):
                    part = part.strip()
                    if part.isdigit():
                        ids_set.add(int(part))

        # 3) Diarios interemedios
        Journal = self.env["account.journal"]
        if "intermediate_diary" in Journal._fields:
            interm_journals = Journal.search([
                ("intermediate_diary", "=", True),
            ])
            ids_set.update(interm_journals.ids)

        # Evita tuplas vacías en SQL
        return tuple(ids_set) or (0,)


    def _initial_balance_sql_q1(self, partners, date_start, account_type):
        journal_id = self.env.company.currency_exchange_journal_id.id
        excluded_journal_ids = self._get_excluded_journal_ids()
        return str(
            self._cr.mogrify(
                """
            SELECT l.partner_id, l.currency_id, l.company_id, l.id,
                CASE WHEN l.balance > 0.0
                    THEN l.balance - sum(coalesce(pd.amount, 0.0))
                    ELSE l.balance + sum(coalesce(pc.amount, 0.0))
                END AS open_amount,
                CASE WHEN l.balance > 0.0
                    THEN l.amount_currency - sum(coalesce(pd.debit_amount_currency, 0.0))
                    ELSE l.amount_currency + sum(coalesce(pc.credit_amount_currency, 0.0))
                END AS open_amount_currency
            FROM account_move_line l
            JOIN account_account aa ON (aa.id = l.account_id)
            JOIN account_move m ON (l.move_id = m.id)
            LEFT JOIN (SELECT pr.*
                FROM account_partial_reconcile pr
                INNER JOIN account_move_line l2
                ON pr.credit_move_id = l2.id
                WHERE l2.date < %(date_start)s
            ) as pd ON pd.debit_move_id = l.id
            LEFT JOIN (SELECT pr.*
                FROM account_partial_reconcile pr
                INNER JOIN account_move_line l2
                ON pr.debit_move_id = l2.id
                WHERE l2.date < %(date_start)s
            ) as pc ON pc.credit_move_id = l.id
            WHERE l.partner_id IN %(partners)s
                AND l.date < %(date_start)s AND not l.blocked
                AND m.state IN ('posted')
                AND m.journal_id NOT IN %(excluded_journal_ids)s
                AND aa.account_type = %(account_type)s
                AND (
                    (pd.id IS NOT NULL AND
                        pd.max_date < %(date_start)s) OR
                    (pc.id IS NOT NULL AND
                        pc.max_date < %(date_start)s) OR
                    (pd.id IS NULL AND pc.id IS NULL)
                )
            GROUP BY l.partner_id, l.currency_id, l.company_id, l.balance, l.id
        """,
                locals(),
            ),
            "utf-8",
        )






    def _display_activity_lines_sql_q1(
        self, partners, date_start, date_end, account_type
    ):
        journal_id = self.env.company.currency_exchange_journal_id.id
        payment_ref = _("Payment")
        excluded_journal_ids = self._get_excluded_journal_ids()

        return str(
            self._cr.mogrify(
                """
            SELECT m.name AS move_id, l.partner_id, l.date,
                array_agg(l.id ORDER BY l.id) as ids,
                CASE WHEN (aj.type IN ('sale', 'purchase'))
                    THEN l.name
                    ELSE '/'
                END as name,
                CASE
                    WHEN (aj.type IN ('sale', 'purchase')) AND l.name IS NOT NULL
                        THEN l.ref
                    WHEN (aj.type in ('bank', 'cash'))
                        THEN %(payment_ref)s
                    ELSE m.ref
                END as case_ref,
                l.blocked, l.currency_id, l.company_id,
                sum(CASE WHEN (l.currency_id is not null AND l.amount_currency > 0.0)
                    THEN l.amount_currency
                    ELSE l.debit
                END) as debit,
                sum(CASE WHEN (l.currency_id is not null AND l.amount_currency < 0.0)
                    THEN l.amount_currency * (-1)
                    ELSE l.credit
                END) as credit,
                CASE WHEN l.date_maturity is null
                    THEN l.date
                    ELSE l.date_maturity
                END as date_maturity
            FROM account_move_line l
            JOIN account_account aa ON (aa.id = l.account_id)
            JOIN account_move m ON (l.move_id = m.id)
            JOIN account_journal aj ON (l.journal_id = aj.id)
            WHERE l.partner_id IN %(partners)s
                AND %(date_start)s <= l.date
                AND l.date <= %(date_end)s
                AND m.state IN ('posted')
                AND m.journal_id NOT IN %(excluded_journal_ids)s
                AND aa.account_type = %(account_type)s
            GROUP BY l.partner_id, m.name, l.date, l.date_maturity,
                CASE WHEN (aj.type IN ('sale', 'purchase'))
                    THEN l.name
                    ELSE '/'
                END, case_ref, l.blocked, l.currency_id, l.company_id
        """,
                locals(),
            ),
            "utf-8",
        )

    def _display_activity_lines_sql_q2(self, sub, company_id):
        return str(
            self._cr.mogrify(
                f"""
            SELECT {sub}.partner_id, {sub}.move_id, {sub}.date, {sub}.date_maturity,
                {sub}.name, {sub}.case_ref as ref, {sub}.debit, {sub}.credit, {sub}.ids,
                {sub}.debit-{sub}.credit as amount, {sub}.blocked,
                COALESCE({sub}.currency_id, c.currency_id) AS currency_id
            FROM {sub}
            JOIN res_company c ON (c.id = {sub}.company_id)
            WHERE c.id = %(company_id)s
        """,
                locals(),
            ),
            "utf-8",
        )


    def _display_activity_reconciled_lines_sql_q2(self, sub, date_end):
        journal_id = self.env.company.currency_exchange_journal_id.id
        excluded_journal_ids = self._get_excluded_journal_ids()

        return str(
            self._cr.mogrify(
                f"""
            SELECT l.id as rel_id, m.name AS move_id, l.partner_id, l.date, l.name,
                l.blocked, l.currency_id, l.company_id, {sub}.id,
            CASE WHEN l.ref IS NOT NULL
                THEN l.ref
                ELSE m.ref
            END as ref,
            CASE WHEN (l.currency_id is not null AND l.amount_currency > 0.0)
                THEN avg(l.amount_currency)
                ELSE avg(l.debit)
            END as debit,
            CASE WHEN (l.currency_id is not null AND l.amount_currency < 0.0)
                THEN avg(l.amount_currency * (-1))
                ELSE avg(l.credit)
            END as credit,
            CASE WHEN l.balance > 0.0
                THEN sum(coalesce(pc.amount, 0.0))
                ELSE -sum(coalesce(pd.amount, 0.0))
            END AS open_amount,
            CASE WHEN l.balance > 0.0
                THEN sum(coalesce(pc.debit_amount_currency, 0.0))
                ELSE -sum(coalesce(pd.credit_amount_currency, 0.0))
            END AS open_amount_currency,
            CASE WHEN l.date_maturity is null
                THEN l.date
                ELSE l.date_maturity
            END as date_maturity
            FROM {sub}
            LEFT JOIN account_partial_reconcile pd ON (
                pd.debit_move_id = {sub}.id AND pd.max_date <= %(date_end)s)
            LEFT JOIN account_partial_reconcile pc ON (
                pc.credit_move_id = {sub}.id AND pc.max_date <= %(date_end)s)
            LEFT JOIN account_move_line l ON (
                pd.credit_move_id = l.id OR pc.debit_move_id = l.id)
            LEFT JOIN account_move m ON (l.move_id = m.id)
            WHERE l.date <= %(date_end)s AND m.state IN ('posted') AND m.journal_id NOT IN %(excluded_journal_ids)s
            GROUP BY l.id, l.partner_id, m.name, l.date, l.date_maturity, l.name,
                CASE WHEN l.ref IS NOT NULL
                    THEN l.ref
                    ELSE m.ref
                END, {sub}.id,
                l.blocked, l.currency_id, l.balance, l.amount_currency, l.company_id
        """,
                locals(),
            ),
            "utf-8",
        )
