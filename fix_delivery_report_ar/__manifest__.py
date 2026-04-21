{
    "name": "Fix Delivery Slip Report",
    "version": "17.0.1.0.0",
    "author": "Andrés Iglesias / Primate Uy",
    "category": "Inventory",
    "description": "Este modulo corrige el reporte de recibo de entrega que rompe la localizacion Argentina al instalar el modulo de stock. El reporte se muestra correctamente tanto para la localizacion Argentina (l10n_ar_stock), imprime el reporte nativo y lo mejora.",
    "depends": ["stock", "l10n_ar_stock"],
    "data": [
        "views/report_delivery_document_native.xml",
        "views/report_deliveryslip.xml",
    ],
    "installable": True,
    "application": False,
}
