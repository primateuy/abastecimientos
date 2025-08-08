# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    cotizacionDia = fields.Float(string='Cotización del día', digits=(12, 6), 
                               help='Cotización del día de la moneda secundaria.', store=True, group_operator=False)
    valorMonedaSecundaria = fields.Monetary(string='Valor en moneda secundaria',
                                          currency_field='moneda_reporte_id',
                                          help='Valor en la moneda de reporte.', store=True)
    
    unit_cost_report = fields.Float(string='Costo unitario MR',
                                  digits='Product Price',
                                  compute='_compute_unit_cost_report',
                                  store=True)
    
    moneda_reporte_id = fields.Many2one(
        'res.currency',
        string='Moneda Secundaria',
        related='company_id.monedaDeReporte',
        store=True,
        help="Moneda secundaria para reportes contables"
    )

    ucmr = fields.Monetary(
    string='UCMR',
    currency_field='moneda_reporte_id',
    help='Último costo en moneda de reporte.',
    store=True,
    group_operator=False,
)

    unitCostesDestinoInc = fields.Float(
        string='Costo total unitario',
        digits='Product Price',
        help='Costo unitario de destino en moneda principal.',
        group_operator=False,
    )

    unitCostesDestinoIncMR = fields.Float(
        string='Costo total unitario MR',
        digits='Product Price',
        help='Costo unitario de destino en moneda reporte.',
        group_operator=False,
    )

    valorizadoCosteDestino = fields.Float(
        string='Valorizado Coste Destino',
        digits='Product Price',
        help='Valorizado del coste de destino en moneda principal.',
        group_operator=False,
    )

    valorizadoCosteDestinoMR = fields.Float(
        string='Valorizado Coste Destino MR',
        digits='Product Price',
        help='Valorizado del coste de destino en moneda principal.',
        group_operator=False,
    )


    inverse_company_rate = fields.Char(
    string="Cotización del día",
    compute='computeInverseCompanyRate',
    store=False
    )

    company_rate = fields.Char(
        string="Cotización del día inversa",
        compute= 'computeCompanyRate',
        store=False
       
    )

    quantity_display = fields.Char(
        string='Quantity Display',
        compute='_compute_quantity_display',
        store=False
    )


    @api.model
    def _read_group_orderby(self, orderby, read_group_orderby, domain):
        
        
        campos_problematicos = [
            "unitCostesDestinoIncMR", 
            "unitCostesDestinoInc", 
            "valorizadoCosteDestino", 
            "valorizadoCosteDestinoMR",
            "quantity_display",
            "inverse_company_rate",
            "company_rate",
            "ucmr"
        ]
        
        if orderby and any(campo in orderby for campo in campos_problematicos):
            return "", [], [] 
        
        result = super()._read_group_orderby(orderby, read_group_orderby, domain)
        return result
    
    def _compute_quantity_display(self):
        for record in self:
            # Comparar con 0 numérico y manejar posibles valores None
            record.quantity_display = '' if record.quantity == 0 else str(record.quantity)

    @api.depends('cotizacionDia', 'moneda_reporte_id', 'company_id.currency_id')
    def computeCompanyRate(self):
        for record in self:
            if record.cotizacionDia and record.moneda_reporte_id and record.company_id.currency_id:
       
                record.company_rate = "{:.2f} {}".format(
                    1/record.cotizacionDia if record.cotizacionDia != 0 else 0,  
                    record.company_id.currency_id.name  
                )
            else:
                record.company_rate = "-"


    @api.depends('cotizacionDia', 'moneda_reporte_id', 'company_id.currency_id')
    def computeInverseCompanyRate(self):
        for record in self:
            if record.cotizacionDia and record.moneda_reporte_id and record.company_id.currency_id:
                
                record.inverse_company_rate = "{:.2f} {}".format(
                    record.cotizacionDia,
                    record.moneda_reporte_id.name 
                )
                
            else:
                record.inverse_company_rate = "-"

    @api.depends('unit_cost', 'cotizacionDia')
    def _compute_unit_cost_report(self):
        for layer in self:
            layer.unit_cost_report = layer.unit_cost * (layer.cotizacionDia or 1)





    @api.model
    def create(self, vals):
        company_id = vals.get('company_id') or self.env.company.id
        company = self.env['res.company'].browse(company_id)
        product = self.env['product.product'].browse(vals.get('product_id'))
        moneda_reporte = company.monedaDeReporte;
        fecha = vals.get('create_date') or fields.Date.context_today(self)
        cantidad_svl = vals.get('quantity', 0)
        if cantidad_svl == 0:
            cantidad_svl = 1;
        
        # 1. Verificar y convertir a moneda principal si es necesario
        currency_id = vals.get('currency_id')
        if currency_id and currency_id != company.currency_id.id:
            currency = self.env['res.currency'].browse(currency_id) or 1;
            

            # Convertir el valor a moneda principal
            value_in_company_currency = currency._convert(
                vals.get('value', 0),
                company.currency_id,
                company,
                fecha
            )
            
            vals.update({
                'value': value_in_company_currency,
                'currency_id': company.currency_id.id,
                'original_currency_id': currency_id,  
                'original_value': vals.get('value') 
            })

        # ENTRADA de stock (compra, ajuste positivo, etc.)
        if moneda_reporte and 'value' in vals and vals.get('value', 0) > 0:
            fecha = vals.get('create_date') or fields.Date.context_today(self)
            cotizacion = self.env['res.currency']._get_conversion_rate(
                company.currency_id,
                moneda_reporte,
                company,
                fecha
            )

            if not cotizacion:
                    raise UserError("No hay cotización disponible para la moneda de reportes en la fecha del pago.")

            vals.update({
                'cotizacionDia': cotizacion,
                'valorMonedaSecundaria': float(vals['value']) * cotizacion,
                'moneda_reporte_id': moneda_reporte.id,
                'unitCostesDestinoInc': (float(vals['value'])) / cantidad_svl,
                'unitCostesDestinoIncMR': (float(vals['value']) * cotizacion) / cantidad_svl,
                'valorizadoCosteDestino': float(vals['value']),
                'valorizadoCosteDestinoMR': float(vals['value']) * cotizacion,
            })

            
        elif moneda_reporte and 'value' in vals and vals.get('value', 0) < 0 and vals.get('product_id'):
            


            cotizacion = self.env['res.currency']._get_conversion_rate(
                company.currency_id,
                moneda_reporte,
                company,
                fecha
            )

            
            if cotizacion:
                vals.update({
                    'cotizacionDia': cotizacion or 1.0,
                    'valorMonedaSecundaria': float(vals['value']) * cotizacion,
                    'moneda_reporte_id': moneda_reporte.id,
                    'unitCostesDestinoInc': float(vals['value']),
                    'unitCostesDestinoIncMR': float(vals['value']) * cotizacion,
                    'valorizadoCosteDestino': float(vals['value']),
                    'valorizadoCosteDestinoMR': float(vals['value']) * cotizacion,
            
                    
                })
            else:
                vals.update({
                    'cotizacionDia': 0.0,
                    'valorMonedaSecundaria': 0.0,
                    'moneda_reporte_id': False,
                    
                })
        else:
            vals.update({
                'cotizacionDia': 0.0,
                'valorMonedaSecundaria': 0.0,
                'moneda_reporte_id': False
            })

        vals['ucmr'] = vals['unit_cost'] * vals.get('cotizacionDia', 1.0);
        

        res = super().create(vals)
        return res



class ResCompany(models.Model):
    _inherit = 'res.company'

    monedaDeReporte = fields.Many2one(
        'res.currency',
        string='Moneda de Reportes',
        help='Moneda que se usará para los valores históricos.'
    )

class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    stock_valuation_layer_ids = fields.One2many(
        'stock.valuation.layer',
        'product_id',
        string='Capas de valoración'
    )
    
    ultimo_costo_mr = fields.Float(
        string='UCMR',
        digits='Product Price',
        help="Último costo histórico en moneda de reportes",
        compute='_compute_ultimo_costo_mr',
        store=True,
        
    )

    @api.depends('stock_valuation_layer_ids.unit_cost_report')
    def _compute_ultimo_costo_mr(self):
        for product in self:
            last_layer = self.env['stock.valuation.layer'].search([
                ('product_id', '=', product.id),
                ('remaining_qty', '>', 0)
            ], order='create_date desc', limit=1)
            
            if last_layer:
                product.ultimo_costo_mr = last_layer.unit_cost_report
            else:
                company = product.company_id or self.env.company
                if company.monedaDeReporte:
                    exchange_rate = self.env['res.currency']._get_conversion_rate(
                        company.currency_id,
                        company.monedaDeReporte,
                        company,
                        fields.Date.today()
                    )
                    product.ultimo_costo_mr = product.standard_price * exchange_rate
                else:
                    product.ultimo_costo_mr = 0.0

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    ultimo_costo_mr = fields.Float(
        string='UCMR',
        digits='Product Price',
        help="Último costo histórico en moneda de reportes",
        compute='_compute_template_ultimo_costo_mr',
        store=True,
    )

    @api.depends('product_variant_ids.ultimo_costo_mr')
    def _compute_template_ultimo_costo_mr(self):
        for template in self:
            if template.product_variant_ids:
                template.ultimo_costo_mr = template.product_variant_ids[0].ultimo_costo_mr
            else:
                template.ultimo_costo_mr = 0.0


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    valor_moneda_reportes = fields.Monetary(
        string='Valor en MR',
        currency_field='moneda_reportes_id',
        help="Valor en moneda de reportes al tipo de cambio histórico"
    )
    moneda_reportes_id = fields.Many2one(
        'res.currency',
        related='company_id.monedaDeReporte',
        string='Moneda de Reportes'
    )
    cotizacion_historica = fields.Float(
        string='Tipo de Cambio Histórico',
        digits=(12, 6)
    )

    @api.model
    def _stock_account_get_lines_vals(self, move, qty, cost):
        vals = super()._stock_account_get_lines_vals(move, qty, cost)

        # Buscar la SVL exacta de la operación (no solo la última entrada)
        svl = self.env['stock.valuation.layer'].search([
            ('stock_move_id', '=', move.id),
            ('product_id', '=', move.product_id.id),
            ('company_id', '=', move.company_id.id)
        ], order='create_date desc', limit=1)

        if svl and svl.moneda_reporte_id:
            for line in vals:
                line.update({
                    'valor_moneda_reportes': abs(line.get('balance', 0)) * svl.cotizacionDia,
                    'cotizacion_historica': svl.cotizacionDia,
                    'moneda_reportes_id': svl.moneda_reporte_id.id
                })
        else:
            for line in vals:
                line.update({
                    'valor_moneda_reportes': 0.0,
                    'cotizacion_historica': 0.0,
                    'moneda_reportes_id': False
                })
        return vals

    def _compute_moneda_reportes_values(self):
        """Método para recalcular valores existentes"""
        for line in self.filtered(lambda l: l.product_id and l.move_id.stock_move_id):
            svl = self.env['stock.valuation.layer'].search([
                ('product_id', '=', line.product_id.id),
                ('remaining_qty', '>', 0),
                ('company_id', '=', line.company_id.id)
            ], order='create_date desc', limit=1)

            if svl and svl.moneda_reporte_id:
                line.write({
                    'valor_moneda_reportes': abs(line.balance) * svl.cotizacionDia,
                    'cotizacion_historica': svl.cotizacionDia,
                    'moneda_reportes_id': svl.moneda_reporte_id.id
                })

    @api.model
    def update_existing_moves(self):
        """Método para actualizar asientos existentes"""
        moves = self.env['account.move'].search([
            ('stock_move_id', '!=', False),
            ('state', '=', 'posted')
        ])
        
        moves.mapped('line_ids')._compute_moneda_reportes_values()


class StockMove(models.Model):
    _inherit = 'stock.move'

    

    def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description):
        vals = super()._generate_valuation_lines_data(partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description)
        
        svl = self.env['stock.valuation.layer'].browse(svl_id)
        
        if svl and svl.moneda_reporte_id:
           
            for line_type in vals:
                if 'balance' in vals[line_type]:
                    amount = abs(vals[line_type]['balance'])
                    vals[line_type].update({
                        'valor_moneda_reportes': amount * svl.cotizacionDia,
                        'cotizacion_historica': svl.cotizacionDia,
                        'moneda_reportes_id': svl.moneda_reporte_id.id
                    })
        
        return vals


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    def button_validate(self):
        res = super().button_validate()

        for landed_cost in self:
            for val_line in landed_cost.valuation_adjustment_lines:
                move = val_line.move_id

                # Solo tomamos los SVL creados POR el landed cost
                svls = self.env['stock.valuation.layer'].search([
                    ('stock_move_id', '=', move.id),
                    ('quantity', '=', 0),
                    ('company_id', '=', move.company_id.id)
                ])

                svlProd = self.env['stock.valuation.layer'].search([
                    ('stock_move_id', '=', move.id),
                    ('quantity', '!=', 0),
                    ('company_id', '=', move.company_id.id)
                ])

                cotizacion = svlProd.cotizacionDia;
                qty = move.product_qty or 1.0
                final_cost_unit = val_line.final_cost / qty if qty != 0 else 0.0
                svlProd.write({
                    'unitCostesDestinoInc': final_cost_unit,
                    'unitCostesDestinoIncMR': final_cost_unit * cotizacion,
                    'valorizadoCosteDestino': val_line.final_cost,
                    'valorizadoCosteDestinoMR': val_line.final_cost * cotizacion,
                })

                for svl in svls:
                    if svl.cotizacionDia and val_line.final_cost:
                        
                        cot = svl.cotizacionDia

                        svl.write({
                            'unitCostesDestinoInc': final_cost_unit,
                            'unitCostesDestinoIncMR': final_cost_unit * cot,
                            'valorizadoCosteDestino': val_line.final_cost,
                            'valorizadoCosteDestinoMR': val_line.final_cost * cot,
                            'ucmr': svlProd.ucmr if svlProd.ucmr else 0.0
                        });

        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _create_invoices(self):
        
        invoices = super()._create_invoices()
        
        
        return invoices


class AccountMove(models.Model):
    _inherit = 'account.move'

    valor_moneda_reportes = fields.Monetary(
        string='Valor Total en MR',
        currency_field='moneda_reportes_id',
        compute='_compute_moneda_reportes_totals',
        store=True,
        help="Valor total del asiento en moneda de reportes"
    )
    
    moneda_reportes_id = fields.Many2one(
        'res.currency',
        related='company_id.monedaDeReporte',
        string='Moneda de Reportes',
        store=True
    )
    
    cotizacion_historica = fields.Float(
        string='Tipo de Cambio Histórico',
        digits=(12, 6),
        compute='_compute_moneda_reportes_totals',
        store=True,
        help="Tipo de cambio histórico promedio del asiento"
    )

    @api.depends('line_ids.valor_moneda_reportes', 'line_ids.cotizacion_historica')
    def _compute_moneda_reportes_totals(self):
        for move in self:
            total_mr = sum(abs(line.valor_moneda_reportes) for line in move.line_ids.filtered(lambda l: l.debit > 0))
            
            # Calcular cotización promedio ponderada
            total_balance = sum(abs(line.balance) for line in move.line_ids.filtered(lambda l: l.debit > 0))
            if total_balance > 0:
                cotizacion_promedio = total_mr / total_balance
            else:
                cotizacion_promedio = 0.0
            
            move.valor_moneda_reportes = total_mr
            move.cotizacion_historica = cotizacion_promedio

    def action_post(self):
        res = super().action_post()
        for invoice in self:
            company = invoice.company_id
            if company.monedaDeReporte and invoice.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                stock_lines = invoice.line_ids.filtered(
                    lambda l: hasattr(l.account_id, 'user_type_id') and l.account_id.user_type_id.type in ('other', 'asset') and l.product_id
                )
                
                cotizacion = self.env['res.currency']._get_conversion_rate(
                    company.currency_id,
                    company.monedaDeReporte,
                    company,
                    invoice.invoice_date or fields.Date.context_today(self)
                )

                if not cotizacion:
                    raise UserError("No hay cotización disponible para la moneda de reportes en la fecha del pago.")

                for line in invoice.line_ids:
                    line.write({
                        'valor_moneda_reportes': abs(line.balance) * cotizacion,
                        'cotizacion_historica': cotizacion
                    })
        return res

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        for payment in self:




            company = payment.company_id
            
            # if payment.currency_id != company.currency_id:
            #     raise UserError("La moneda del pago debe coincidir con la moneda de la empresa (%s)." % payment.company_id.currency_id.name)

            if company.monedaDeReporte:
                cotizacion = self.env['res.currency']._get_conversion_rate(
                    company.currency_id,
                    company.monedaDeReporte,
                    company,
                    payment.date or fields.Date.context_today(self)
                )

                if not cotizacion:
                    raise UserError("No hay cotización disponible para la moneda de reportes en la fecha del pago.")

                for line in payment.line_ids:

                    line.valor_moneda_reportes = abs(line.balance) * cotizacion
                    line.cotizacion_historica = cotizacion
                    line.moneda_reportes_id = company.monedaDeReporte.id
            

        
        res = super().action_post()
        return res


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):

        # for order in self:
        #     if order.company_id.currency_id != order.currency_id:
        #         raise UserError("La moneda del pedido debe coincidir con la moneda principal de la empresa (%s)." % order.company_id.currency_id.name)


        res = super().button_confirm()       


        return res;