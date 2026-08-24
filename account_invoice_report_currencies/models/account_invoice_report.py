# -*- coding: utf-8 -*-
from odoo import models, fields, api

# Signo aplicado a las medidas para que sean coherentes con price_subtotal /
# price_total del reporte del core: ventas en positivo, compras en negativo.
SIGNO_POR_TIPO = (
    "(CASE WHEN move.move_type IN ('in_invoice', 'out_refund', 'in_receipt') "
    "THEN -1 ELSE 1 END)"
)


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    moneda_reportes_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda de Reportes',
        readonly=True,
    )
    valor_moneda_reportes = fields.Monetary(
        string='Valor en MR',
        currency_field='moneda_reportes_id',
        readonly=True,
        help="Importe de la línea en la moneda de reportes de la compañía, "
             "valorizado al tipo de cambio histórico. Lo alimenta el módulo "
             "tchistorico; las líneas sin valorizar aportan cero.",
    )
    secondary_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Divisa secundaria',
        readonly=True,
    )
    amount_secondary = fields.Monetary(
        string='Importe Divisa Secundaria',
        currency_field='secondary_currency_id',
        readonly=True,
        help="Importe de la línea en la divisa secundaria de la compañía. Lo "
             "alimenta el módulo aml_secondary_currency mediante el asistente "
             "de cálculo; queda en cero hasta que se ejecute.",
    )

    @api.model
    def _select(self):
        # Se agregan las columnas de ambos módulos de moneda. Las monedas se
        # leen de res_company porque en account.move.line son campos related
        # sin almacenar, es decir no existen como columna.
        #
        # valor_moneda_reportes se guarda siempre en positivo (es una
        # magnitud), así que se le aplica el signo según tipo de documento.
        #
        # amount_secondary en cambio se guarda como debit - credit, o sea con
        # la misma orientación que balance, por lo que alcanza con invertirlo
        # igual que hace el core con price_subtotal.
        #
        # Ninguna de las dos se multiplica por currency_table.rate: ya vienen
        # expresadas en su moneda de destino y convertirlas las rompería.
        return super()._select() + """
                , report_company."monedaDeReporte"                          AS moneda_reportes_id
                , COALESCE(line.valor_moneda_reportes, 0.0) * %(signo)s     AS valor_moneda_reportes
                , report_company.secondary_currency_id                      AS secondary_currency_id
                , -COALESCE(line.amount_secondary, 0.0)                     AS amount_secondary
        """ % {'signo': SIGNO_POR_TIPO}

    @api.model
    def _from(self):
        # Join extra para resolver las monedas configuradas en la compañía.
        return super()._from() + """
                LEFT JOIN res_company report_company ON report_company.id = line.company_id
        """
