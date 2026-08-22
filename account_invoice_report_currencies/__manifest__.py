# -*- coding: utf-8 -*-
{
    'name': 'Análisis de Facturas - Monedas de Reporte',
    'summary': 'Agrega Valor en MR y Divisa Secundaria al análisis de facturas',
    'description': """
Análisis de Facturas - Monedas de Reporte
=========================================

Extiende el reporte ``account.invoice.report`` (Contabilidad > Reportes >
Análisis de facturas) con dos medidas adicionales:

* **Valor en MR**: importe en la moneda de reportes de la compañía, tomado del
  campo ``valor_moneda_reportes`` que alimenta el módulo ``tchistorico``.
* **Importe Divisa Secundaria**: importe en la divisa secundaria de la
  compañía, tomado del campo ``amount_secondary`` del módulo
  ``aml_secondary_currency``.

Ambas medidas quedan disponibles en las vistas pivot, gráfico y lista.

No modifica los módulos de origen: sólo extiende la vista SQL del reporte.
    """,
    'author': 'Primate',
    'category': 'Accounting/Accounting',
    'version': '17.0.1.0.0',
    'depends': [
        'account',
        'tchistorico',
        'aml_secondary_currency',
    ],
    'data': [
        'views/account_invoice_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
