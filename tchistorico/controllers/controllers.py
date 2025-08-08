# -*- coding: utf-8 -*-
# from odoo import http


# class Tchistorico(http.Controller):
#     @http.route('/tchistorico/tchistorico', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/tchistorico/tchistorico/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('tchistorico.listing', {
#             'root': '/tchistorico/tchistorico',
#             'objects': http.request.env['tchistorico.tchistorico'].search([]),
#         })

#     @http.route('/tchistorico/tchistorico/objects/<model("tchistorico.tchistorico"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('tchistorico.object', {
#             'object': obj
#         })

