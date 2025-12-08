# my_module/models/stock_quant_product_location_report.py

from odoo import api, fields, models, tools


class StockQuantProductLocationReport(models.Model):
    _name = "stock.quant.product.location.report"
    _description = "Stock por producto y ubicacion (sin repetidos)"
    _auto = False
    _rec_name = "product_id"
    _order = "product_id, location_id"

    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    product_tmpl_id = fields.Many2one(
        "product.template", string="Plantilla de producto", readonly=True
    )
    location_id = fields.Many2one("stock.location", string="Ubicación", readonly=True)
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)

    quantity = fields.Float("Cantidad disponible", readonly=True)
    reserved_quantity = fields.Float("Cantidad reservada", readonly=True)
    available_quantity = fields.Float("Cantidad no reservada", readonly=True)
    value_report = fields.Float("Valor de Reporte", readonly=True)


    def _select(self):
        return """
            SELECT
                row_number() OVER () AS id,
                sq.product_id AS product_id,
                pp.product_tmpl_id AS product_tmpl_id,
                sq.location_id AS location_id,
                sq.company_id AS company_id,
                sq.value_report AS value_report,
                SUM(sq.quantity) AS quantity,
                SUM(sq.reserved_quantity) AS reserved_quantity,
                SUM(sq.quantity - sq.reserved_quantity) AS available_quantity
        """

    def _from(self):
        return """
            FROM stock_quant sq
            JOIN product_product pp ON pp.id = sq.product_id
        """

    def _group_by(self):
        return """
            GROUP BY
                sq.product_id,
                pp.product_tmpl_id,
                sq.location_id,
                sq.company_id,
                sq.value_report
        """

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
            )
            """
            % (self._table, self._select(), self._from(), self._group_by())
        )