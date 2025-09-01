{
    "name": "Lot Cost on Inventory Adjustments",
    "summary": "Permite asignar un costo por Lote y aplicarlo al valorar ajustes de inventario.",
    "version": "17.0",
    "author": "iglesias-andres - Primate Uy",
    "license": "LGPL-3",
    "category": "Inventory",
    "depends": ["stock", "stock_account"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_lot_views.xml",
        # "views/stock_inventory_views.xml"
    ],
    "installable": True,
    "application": False
}
