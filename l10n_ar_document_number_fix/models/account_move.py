# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'


    @api.model
    def _l10n_ar_get_document_number_parts(self, document_number, document_type_code):
        # import shipments
        if document_type_code in ['66', '67']:
            pos = invoice_number = '0'
        else:
            _logger.warning('document number', document_number)
            parts = document_number.split(' ')
            if len(parts) > 1:
                pos, invoice_number = parts[1].split('-')
            else:
                pos, invoice_number = document_number.split('-')

        return {'invoice_number': int(invoice_number), 'point_of_sale': int(pos)}