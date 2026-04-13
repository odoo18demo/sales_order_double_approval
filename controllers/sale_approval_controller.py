from odoo import http
from odoo.http import request

class SaleApprovalController(http.Controller):

    @http.route(
        '/sale_approval/<int:order_id>/<string:token>/<string:action>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def sale_approval(self, order_id, token, action, **kw):
        order = request.env['sale.order'].sudo().search([
            ('id', '=', order_id),
            ('approval_token', '=', token),
        ], limit=1)

        if not order:
            return request.make_response(
                "<html><body style='font-family:Arial;text-align:center;margin-top:80px'>"
                "<h2>⚠️ Invalid or expired approval link.</h2>"
                "</body></html>",
                headers=[('Content-Type', 'text/html')]
            )

        if action == 'approve':
            order.sudo().button_approve()
            order.sudo().message_post(
                body="✅ <b>Approved</b> via email link.",
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
            msg = "✅ Approved"
            color = "#28a745"
            detail = "Sale Order <b>%s</b> has been approved successfully." % order.name

        elif action == 'reject':
            order.sudo().action_cancel()
            order.sudo().message_post(
                body="❌ <b>Rejected</b> via email link.",
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
            msg = "❌ Rejected"
            color = "#dc3545"
            detail = "Sale Order <b>%s</b> has been rejected." % order.name

        else:
            msg = "Invalid action"
            color = "#666"
            detail = "Unknown action requested."

        # ✅ ONLY THIS html VARIABLE CHANGED
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
