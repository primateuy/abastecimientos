# account_invoice_date_importable_plus

Este módulo hace visible el campo `invoice_date` en el asistente de Importar (`account.move`).

## Estructura
- custom-addons/account_invoice_date_importable_plus/__manifest__.py
- custom-addons/account_invoice_date_importable_plus/__init__.py
- custom-addons/account_invoice_date_importable_plus/models/__init__.py
- custom-addons/account_invoice_date_importable_plus/models/account_move_patch.py

## Instalación
1. Copiar la carpeta `account_invoice_date_importable_plus` a `custom-addons/`.
2. Actualizar la lista de apps e instalar el módulo.

Respeta convenciones:
- author: "aiglesas - Primate Uy"
- version: "17"
- Booleans: True/False
- Sin assets en el manifiesto.
