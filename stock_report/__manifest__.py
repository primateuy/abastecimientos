{
    "name": "Reporte de Stock por Almacén",
    "version": "1.0.0",
    "depends": ["stock"],
    "author": "Andrés Iglesias / Primate Uy",
    "category": "Inventory",
    "data": [
        "security/stock_report_security.xml",
        "security/ir.model.access.csv",
        "views/res_users_view.xml",
        "views/stock_report_view.xml",
        "views/stock_warehouse_views.xml"
    ],
    "post_init_hook": "post_init_assign_default_warehouse_group",
    "installable": True,
    "application": False,

}