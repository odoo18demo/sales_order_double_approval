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
                "<h2>Invalid or expired verification URL link.</h2>"
                "</body></html>",
                headers=[('Content-Type', 'text/html')]
            )

        if action in ('approve', 'reject'):
            detail = order.sudo()._process_approval(action, approval_step)
            msg = "Action Processed Successfully" if action == 'approve' else "Revision Required Applied"
            color = "#28a745" if action == 'approve' else "#dc3545"
        else:
            msg = "Action Error"
            color = "#666"
            detail = "An unidentifiable processing step was encountered."

        html = f"""
        <html>
        <head>
            <title>{msg}</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 80px; background-color: #f8f9fa; }}
                .container {{ display: inline-block; padding: 30px; background: #fff; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .badge {{ display: inline-block; padding: 12px 30px; border-radius: 8px;
                         background: {color}; color: white; font-size: 22px; font-weight: bold; }}
                .details {{ font-size: 16px; margin-top: 20px; color: #333; }}
                .counter {{ font-size: 14px; color: #888; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="badge">{msg}</div>
                <p class="details">{detail}</p>
                <p class="counter">This window session will conclude in <b id="sec">4</b> seconds...</p>
            </div>
            <script>
                var s = 4;
                var t = setInterval(function() {{
                    s--;
                    document.getElementById('sec').innerText = s;
                    if (s <= 0) {{
                        clearInterval(t);
                        window.open('', '_self', '');
                        window.close();
                    }}
                }}, 1000);
            </script>
        </body>
        </html>
        """
        return request.make_response(html, headers=[('Content-Type', 'text/html')])