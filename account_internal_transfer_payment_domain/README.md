v2 - Ajuste robusto
-------------------
Este paquete sobrescribe explícitamente el `@api.onchange('is_internal_transfer')` del core
para que **después** de ejecutar la lógica estándar, fuerce el dominio del campo
`payment_method_line_id` e incluya 'Nuevo Cheque de Tercero' (code: new_third_party_checks)
en **transferencias internas** de tipo inbound.

Si otros módulos reemplazan el dominio en ese mismo onchange, esta versión se asegura de
tener la "última palabra" devolviendo un `res['domain']` consolidado.