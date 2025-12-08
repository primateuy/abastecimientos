{
    "name": "TCH Importaciones",
    "version": "17.0.1.0.0",
    "author": "aiglesas - Primate Uy",
    "category": "Inventory",
    "summary": "Modelo de importaciones asociado a traslados para cálculo de costos en destino",
    "depends": [
        "stock",
        "tchistorico",
        'stock_landed_costs'
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        'views/stock_move_report.xml',
        "views/landed_cost_lines.xml",
        "views/landed_cost_lines_search.xml",
        "views/importacion_views.xml",
        "views/stock_valuation_adjustment_lines.xml",

    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3"
}
