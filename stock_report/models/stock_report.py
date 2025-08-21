from odoo import fields, models

class ReportStockByWarehouse(models.Model):
    _name = 'report.stock.by.warehouse'
    _description = 'Reporte de stock por almacén'
    _auto = False

    id = fields.Integer(string='ID', readonly=True)
    product_id = fields.Many2one('product.product', string="Producto")
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén')
    location_id = fields.Many2one('stock.location', string="Ubicación")
    lot_id = fields.Many2one('stock.lot', string="Lote")
    qty_available = fields.Float(string="Stock Real")
    incoming_qty = fields.Float(string="Stock Entrante")
    outgoing_qty = fields.Float(string="Stock Saliente")
    virtual_available = fields.Float(string="Stock Pronosticado")
    daily_consumption = fields.Float(string='Consumo Anual Salidas', readonly=True)
    days_of_stock = fields.Float(string='Stock en Días', readonly=True)
    group_id = fields.Many2one('stock.warehouse.group.report', string="Grupo de almacenes")
    
    def init(self):
        self._cr.execute("""
    CREATE OR REPLACE VIEW report_stock_by_warehouse AS (
        WITH stock_data AS (
            SELECT
                row_number() OVER ()               AS id,
                sq.product_id,
                sq.location_id,
                sw.id                              AS warehouse_id,
                sq.lot_id                          AS lot_id,
                SUM(sq.quantity)                   AS qty_available,
                SUM(sq.reserved_quantity)          AS outgoing_qty,
                COALESCE((
                    SELECT SUM(sm.product_uom_qty)
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.product_id = sq.product_id
                      AND sml.location_dest_id = sq.location_id
                      AND sm.state IN ('confirmed', 'assigned', 'waiting')
                      AND (
                        (sml.lot_id IS NULL AND sq.lot_id IS NULL)
                        OR (sml.lot_id = sq.lot_id)
                      )
                ), 0)                             AS incoming_qty,
                COALESCE((
                    SELECT SUM(sml.quantity)::float / 365
                    FROM stock_move_line sml
                    WHERE sml.product_id = sq.product_id
                      AND sml.location_id = sq.location_id
                      AND sml.state = 'done'
                      AND sml.date >= date_trunc('year', current_date) - interval '1 year'
                      AND sml.date < date_trunc('year', current_date)
                      AND sml.quantity > 0
                      AND sml.location_dest_id != sq.location_id
                ), 0)                             AS daily_consumption,
                sw.group_id AS group_id
            FROM stock_quant sq
            JOIN stock_location sl ON sq.location_id = sl.id
            JOIN stock_warehouse sw ON sl.warehouse_id = sw.id
            GROUP BY
                sq.product_id,
                sq.location_id,
                sw.id,
                sw.group_id,
                sq.lot_id
        )
        SELECT *,
            qty_available + incoming_qty - outgoing_qty AS virtual_available,
            CASE
                WHEN COALESCE(daily_consumption, 0) > 0 THEN qty_available / daily_consumption
                ELSE NULL
            END AS days_of_stock
        FROM stock_data
    );
    """)