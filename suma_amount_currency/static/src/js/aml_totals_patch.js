/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// Guardamos referencia al método original
const originalFormatAggregateValue = ListRenderer.prototype.formatAggregateValue;

patch(ListRenderer.prototype, {
    formatAggregateValue(aggregate, field, group) {
        // Ejecutamos el original
        const original = originalFormatAggregateValue.call(this, aggregate, field, group);

        try {
            const isAml = this.props?.list?.resModel === "account.move.line";
            const groupedBy = this.props?.list?.groupBy || [];
            const isGroupedByCurrency = groupedBy.includes("currency_id");
            const isAmountCurrency = field?.name === "amount_currency";

            if (isAml && isAmountCurrency && !isGroupedByCurrency) {
                // Mostrar vacío o guion si no está agrupado por divisa
                return "—";  // o "" si preferís vacío
            }
        } catch (_) {
            // Si algo falla, devolvemos el original
        }
        return original;
    },
});