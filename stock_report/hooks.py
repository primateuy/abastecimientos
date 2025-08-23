from odoo import 
def post_init_assign_default_warehouse_group(env):
    default_group = env.ref('stock_report.stock_warehouse_group_default', raise_if_not_found=False)
    if default_group:
        env.cr.execute("""
            UPDATE stock_warehouse
            SET group_id = %s
            WHERE group_id IS NULL
        """, (default_group.id,))