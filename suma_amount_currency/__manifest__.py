{
    "name": "Suma segura de Importe en divisa en apuntes contables",
    "version": "17.0",
    "author": "Primate Uy",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "views/account_move_line_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ml_sum_amount_currency/static/src/js/aml_totals_patch.js",
        ],
    },
    "installable": True,
}