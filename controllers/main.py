from odoo import http
from odoo.http import request
import json
import logging
_logger = logging.getLogger(__name__)


class MrpScreen(http.Controller):

    @http.route('/mrp-screen', type='http', auth='user', csrf=False)
    def mrp_screen(self, **kwargs):
        productions = request.env['mrp.production'].search([
            ('state', 'in', ['confirmed', 'progress', 'to_close'])
        ], order='date_start asc')

        product_map = {}
        for mo in productions:
            pid = mo.product_id.id
            customer = 'No Customer'

            try:
                if mo.origin:
                    origin_ref = mo.origin.strip().split(',')[0].strip()
                    sale_order = request.env['sale.order'].sudo().search([
                        ('name', '=', origin_ref)
                    ], limit=1)
                    if sale_order and sale_order.partner_id:
                        customer = sale_order.partner_id.name or 'No Customer'

            except Exception as e:
                _logger.error("Error getting customer for MO %s: %s", mo.name, e)
                customer = 'No Customer'

            # ✅ Log AFTER setting customer
            _logger.info("MO: %s | Origin: %s | Customer: %s",
                         mo.name, mo.origin, customer)

            if pid not in product_map:
                product_map[pid] = {
                    'product_name': mo.product_id.name,
                    'total_qty': 0,
                    'uom': mo.product_uom_id.name,
                    'orders': [],
                }

            product_map[pid]['total_qty'] += mo.product_qty
            product_map[pid]['orders'].append({
                'mo_name': mo.name,
                'origin': mo.origin or '—',
                'customer': customer,
                'qty': mo.product_qty,
                'state': mo.state,
                'date': str(mo.date_start) if mo.date_start else '—',
            })

        products = list(product_map.values())
        for prod in products:
            prod['orders_json'] = json.dumps(prod['orders'], ensure_ascii=False)

        products_json = json.dumps(products, ensure_ascii=False)

        return request.render(
            'sales_order_double_approval.mrp_screen_template',
            {
                'productions': productions,
                'products': products,
                'products_json': products_json,
            }
        )