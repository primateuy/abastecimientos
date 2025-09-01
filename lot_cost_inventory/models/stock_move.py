from odoo import models

class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_price_unit(self):
        """
        Odoo 17: usar costo del lote SOLO para ENTRADAS por AJUSTE DE INVENTARIO,
        y solo si el lote tiene lot_unit_cost > 0. Evitar depender de qty_done,
        porque puede no estar disponible en este punto del flujo.
        """
        self.ensure_one()
        native_price = super()._get_price_unit()

        # ¿Es un movimiento de ajuste? (alguna ubicación es 'inventory')
        is_inventory_move = (
            (self.location_id and self.location_id.usage == "inventory")
            or (self.location_dest_id and self.location_dest_id.usage == "inventory")
        )
        if not is_inventory_move:
            return native_price

        # Solo ENTRADAS por ajuste: destino NO 'inventory' (típicamente interno)
        # Si el destino es 'inventory', interpretamos BAJA y volvemos al nativo.
        if self.location_dest_id and self.location_dest_id.usage == "inventory":
            return native_price

        # Recolectar líneas con LOTE y costo de lote > 0
        lines = self.move_line_ids.filtered(lambda ml: ml.lot_id and (ml.lot_id.lot_unit_cost or 0.0) > 0.0)
        if not lines:
            return native_price

        def _line_qty(ml):
            """Cantidad efectiva de la línea, tolerante a distintas fases del flujo."""
            # 1) qty_done si existe
            q = getattr(ml, "qty_done", None)
            if q is not None:
                return q
            # 2) quantity (algunas ramas/contexts)
            q = getattr(ml, "quantity", None)
            if q is not None:
                return q
            # 3) product_uom_qty como fallback
            return getattr(ml, "product_uom_qty", 0.0)

        total_qty = 0.0
        total_val = 0.0
        for ml in lines:
            qty = _line_qty(ml)
            if qty and qty > 0:
                total_qty += qty
                total_val += qty * ml.lot_id.lot_unit_cost

        # Si no logramos una cantidad positiva, volvemos al comportamiento nativo
        if total_qty <= 0.0:
            return native_price

        return total_val / total_qty