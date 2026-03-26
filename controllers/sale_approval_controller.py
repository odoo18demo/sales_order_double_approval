from odoo import http
from odoo.http import request

class SaleApprovalController(http.Controller):

    @http.route('/sale_approval/<int:order_id>/<string:token>/<string:action>', type='http', auth='public', website=True)
    def sale_approval(self, order_id, token, action, **kw):
        order = request.env['sale.order'].sudo().search([('id', '=', order_id), ('approval_token', '=', token)], limit=1)
        if not order:
            return "Invalid or expired approval link."

        if action == 'approve':
            order.sudo().button_approve()
            return "Sale Order approved successfully!"
        elif action == 'reject':
            order.sudo().action_cancel()
            return "Sale Order rejected successfully!"
        else:
            return "Invalid action."