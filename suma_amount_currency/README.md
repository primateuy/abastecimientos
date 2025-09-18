# ML - Suma segura de Importe en Divisa

Este módulo extiende la vista de **Apuntes contables** para mostrar de forma
segura el total de `amount_currency` (importe en divisa).

## Motivación

En Odoo, el campo **Importe en divisa** (`amount_currency`) no siempre se puede
sumar de forma directa porque los apuntes pueden involucrar múltiples monedas.
Esto genera resultados confusos o totales incorrectos.

Con este módulo:

- Si los apuntes se **agrupan por divisa** (`currency_id`), se muestra el total
  de `amount_currency` en el pie de grupo.
- En cualquier otro agrupamiento, el campo aparece sin total (o con un guion) 
  para evitar confusión.

## Funcionalidad

- Agrega `group_operator="sum"` al campo `amount_currency` en la vista de árbol
  de **Apuntes contables**.
- Incluye un pequeño **patch en JavaScript** que asegura que el total de
  `amount_currency` sólo se muestre cuando la agrupación es por divisa.
- Evita errores de visualización en escenarios con múltiples monedas.

## Uso

1. Instalar el módulo desde Apps.
2. Ir a **Contabilidad → Apuntes contables**.
3. Agrupar por **Divisa**:
   - Se mostrará el total de `amount_currency` por cada grupo de divisa.
4. Agrupar por cualquier otro campo:
   - La columna `Importe en divisa` no mostrará totales.