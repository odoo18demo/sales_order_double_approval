from odoo import http
from odoo.http import request

class SaleApprovalController(http.Controller):

    @http.route(
        '/sale_approval/<int:order_id>/<string:token>/<string:action>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )  # ← removed website=True
    def sale_approval(self, order_id, token, action, **kw):
        order = request.env['sale.order'].sudo().search([
            ('id', '=', order_id),
            ('approval_token', '=', token),
        ], limit=1)

        if not order:
            return request.make_response(
                "<h2>⚠️ Invalid or expired approval link.</h2>",
                headers=[('Content-Type', 'text/html')]
            )

        if action == 'approve':
            order.sudo().button_approve()
            msg = "<h2 style='color:green'>✅ Sale Order <b>%s</b> approved successfully!</h2>" % order.name
        elif action == 'reject':
            order.sudo().action_cancel()
            msg = "<h2 style='color:red'>❌ Sale Order <b>%s</b> rejected successfully!</h2>" % order.name
        else:
            msg = "<h2>Invalid action.</h2>"

        return request.make_response(
            "<html><body style='font-family:Arial;text-align:center;margin-top:80px'>%s"
            "<p>You can close this window.</p></body></html>" % msg,
            headers=[('Content-Type', 'text/html')]
        )