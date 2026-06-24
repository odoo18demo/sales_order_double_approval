from odoo import http
from odoo.http import request
import json
import logging
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class MrpScreen(http.Controller):

    @http.route('/mrp-screen', type='http', auth='user', csrf=False)
    def mrp_screen(self, **kwargs):

        all_productions = request.env['mrp.production'].sudo().search([
            ('state', 'in', ['draft', 'confirmed', 'progress', 'to_close', 'done'])
        ], order='date_start asc')

        productions = request.env['mrp.production']
        product_map = {}

        processed_so_lines = set()

        for mo in all_productions:
            if not mo.origin:
                continue
            origin_ref = mo.origin.strip().split(',')[0].strip()
            sale_order = request.env['sale.order'].sudo().search([
                ('name', '=', origin_ref),
                ('state', '=', 'sale')
            ], limit=1)

            if not sale_order:
                continue

            pid = mo.product_id.id

            so_product_key = f"{sale_order.id}_{pid}"
            if so_product_key in processed_so_lines:
                continue

            sale_lines = sale_order.order_line.filtered(lambda l: l.product_id.id == pid)
            if not sale_lines:
                continue

            ordered_qty = sum(sale_lines.mapped('product_uom_qty'))
            delivered_qty = sum(sale_lines.mapped('qty_delivered'))

            remaining_qty = ordered_qty - delivered_qty

            if remaining_qty <= 0:
                continue

            processed_so_lines.add(so_product_key)
            productions |= mo

            customer = (
                sale_order.partner_id.name
                if sale_order.partner_id
                else 'No Customer'
            )

            if pid not in product_map:
                product_map[pid] = {
                    'product_name': mo.product_id.name,
                    'total_qty': 0,
                    'uom': mo.product_uom_id.name,
                    'color': mo.product_id.product_tmpl_id.prod_color or '', # <-- ADDED TOP-LEVEL COLOR HERE
                    'orders': [],
                }

            delivery_date = '—'
            picking = request.env['stock.picking'].sudo().search([
                ('sale_id', '=', sale_order.id),
                ('state', 'not in', ['cancel'])
            ], order='scheduled_date asc', limit=1)
            if picking and picking.scheduled_date:
                try:
                    delivery_date = picking.scheduled_date.strftime('%d-%m-%Y')
                except Exception:
                    delivery_date = str(picking.scheduled_date)

            product_map[pid]['total_qty'] += remaining_qty

            order_date_str = '—'
            if sale_order.date_order:
                order_date_str = sale_order.date_order.strftime('%d-%m-%Y')

            product_map[pid]['orders'].append({
                'mo_name': mo.name,
                'origin': mo.origin or '—',
                'customer': customer,
                'customer_city': (
                    sale_order.partner_id.city
                    if sale_order.partner_id
                    else '—'
                ),
                'salesperson': (
                    sale_order.user_id.name
                    if sale_order.user_id
                    else '—'
                ),
                'item_name': mo.product_id.name or '—',
                'color': mo.product_id.product_tmpl_id.prod_color or '',
                'delivery_date': delivery_date,
                'note': html2plaintext(sale_order.display_note) if sale_order.display_note else '',
                'qty': remaining_qty,
                'state': mo.state,
                'date_order': order_date_str,
                'date': (
                    str(mo.date_start)
                    if mo.date_start
                    else '—'
                ),
            })

        products = list(product_map.values())
        for prod in products:
            prod['orders_json'] = json.dumps(
                prod['orders'],
                ensure_ascii=False
            )

        products_json = json.dumps(products, ensure_ascii=False)

        return request.render(
            'sales_order_double_approval.mrp_screen_template',
            {
                'productions': productions,
                'products': products,
                'products_json': products_json,
            }
        )