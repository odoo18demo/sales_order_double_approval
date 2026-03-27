from odoo import http
from odoo.http import request

class MrpScreen(http.Controller):

    @http.route('/mrp-screen', type='http', auth='public', csrf=False)
    def mrp_screen(self, **kwargs):
        productions = request.env['mrp.production'].sudo().search([
            ('state', 'in', ['confirmed', 'progress', 'to_close'])
        ], order='date_start asc')

        return request.render(
            'sales_order_double_approval.mrp_screen_template',
            {'productions': productions}
        )