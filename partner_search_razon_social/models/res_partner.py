from odoo import models, api

class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _name_search(
        self,
        name='',
        args=None,
        operator='ilike',
        limit=100,
        name_get_uid=None,
        order=None,
    ):
        """
        - Busca por social_reason (fallback: name).
        - EXCLUYE contactos relacionados (hijos): sólo empresas o personas sin parent_id.
        """
        args = list(args or [])

        # Sólo empresas o personas "raíz" (sin padre).
        only_companies_or_root_persons = ['|', ('is_company', '=', True), ('parent_id', '=', False)]

        if name:
            search_part = ['|', ('social_reason', operator, name), ('name', operator, name)]
            domain = ['&'] + only_companies_or_root_persons + search_part + args
        else:
            domain = only_companies_or_root_persons + args

        return self._search(
            domain,
            limit=limit,
            access_rights_uid=name_get_uid,
            order=order,
        )

    def _compute_display_name(self):
        """
        En Odoo 17, Many2one suele usar display_name.
        Recalculamos para priorizar social_reason y, si es contacto hijo, agregamos (padre).
        """
        # Primero dejá que el core calcule su versión
        super()._compute_display_name()

        for p in self:
            base = p.social_reason or p.name or ""
            if p.parent_id and not p.is_company:
                parent_disp = p.parent_id.social_reason or p.parent_id.name or ""
                if parent_disp:
                    base = f"{base} ({parent_disp})"
            p.display_name = base
            
    def name_get(self):
        return [(p.id, p.display_name) for p in self]