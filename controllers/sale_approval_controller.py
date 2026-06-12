from odoo import http
from odoo.http import request

class SaleApprovalController(http.Controller):

    @http.route(
        [
            '/sale_approval/<int:order_id>/<string:token>/<string:action>',
            '/sale_approval/<int:order_id>/<string:token>/<string:approval_step>/<string:action>',
        ],
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def sale_approval(self, order_id, token, action, approval_step='revisor', **kw):
        order = request.env['sale.order'].sudo().search([
            ('id', '=', order_id),
            ('approval_token', '=', token),
        ], limit=1)

        if not order:
            return request.make_response(
                "<html><body style='font-family:Arial;text-align:center;margin-top:80px'>"
                "<h2>Invalid or expired approval link.</h2>"
                "</body></html>",
                headers=[('Content-Type', 'text/html')]
            )

        if action in ('approve', 'reject'):
            detail = order.sudo()._process_approval(action, approval_step)
            msg = "Approved" if action == 'approve' else "Revision Required"
            color = "#28a745" if action == 'approve' else "#dc3545"
        else:
            msg = "Invalid action"
            color = "#666"
            detail = "Unknown action requested."

        html = """
        <html>
        <head>
            <title>%s</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; margin-top: 80px; }
                .badge { display: inline-block; padding: 12px 30px; border-radius: 8px;
                         background: %s; color: white; font-size: 22px; font-weight: bold; }
                .counter { font-size: 14px; color: #888; margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="badge">%s</div>
            <p style="font-size:16px; margin-top:20px;">%s</p>
            <p class="counter">This tab will close in <b id="sec">3</b> seconds...</p>
            <script>
                var s = 3;
                var t = setInterval(function() {
                    s--;
                    document.getElementById('sec').innerText = s;
                    if (s <= 0) {
                        clearInterval(t);
                        window.open('', '_self', '');
                        window.close();
                    }
                }, 1000);
            </script>
        </body>
        </html>
        """ % (msg, color, msg, detail)

        return request.make_response(
            html,
            headers=[('Content-Type', 'text/html')]
        )
