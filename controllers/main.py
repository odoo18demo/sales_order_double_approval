from odoo import http
from odoo.http import request
import json
import logging
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class MrpScreen(http.Controller):

    @http.route('/mrp-screen', type='http', auth='user', csrf=False)
    def mrp_screen(self, **kwargs):

        # 1. ADDED 'done' state. We need to keep tracking MOs even after production,
        # until the inventory delivery is actually validated.
        all_productions = request.env['mrp.production'].sudo().search([
            ('state', 'in', ['draft', 'confirmed', 'progress', 'to_close', 'done'])
        ], order='date_start asc')

        productions = request.env['mrp.production']
        product_map = {}

        # We use a set to track which SO + Product combinations we have already processed.
        # This prevents duplicate lines on the screen if Odoo creates backorder MOs.
        processed_so_lines = set()

        for mo in all_productions:
            # Skip if no origin
            if not mo.origin:
                continue
            origin_ref = mo.origin.strip().split(',')[0].strip()
            sale_order = request.env['sale.order'].sudo().search([
                ('name', '=', origin_ref),
                ('state', '=', 'sale')
            ], limit=1)

            # Skip if SO not confirmed
            if not sale_order:
                continue

            pid = mo.product_id.id

            # 2. Check if we already processed this product for this specific Sale Order
            so_product_key = f"{sale_order.id}_{pid}"
            if so_product_key in processed_so_lines:
                continue

            # 3. Look at the ACTUAL Sales Order Lines to find out how many were delivered
            sale_lines = sale_order.order_line.filtered(lambda l: l.product_id.id == pid)
            if not sale_lines:
                continue

            ordered_qty = sum(sale_lines.mapped('product_uom_qty'))
            delivered_qty = sum(sale_lines.mapped('qty_delivered'))

            # Qty left to deliver to the customer
            remaining_qty = ordered_qty - delivered_qty

            # 4. If the product is fully delivered, hide it from the manufacturing screen!
            if remaining_qty <= 0:
                continue

            # Mark this SO+Product combo as processed so we don't repeat it
            processed_so_lines.add(so_product_key)

            # Add valid MO
            productions |= mo

            customer = (
                sale_order.partner_id.name
                if sale_order.partner_id
                else 'No Customer'
            )

            _logger.info(
                "MO: %s | SO: %s | Customer: %s | Remaining Qty: %s",
                mo.name,
                sale_order.name,
                customer,
                remaining_qty
            )

            if pid not in product_map:
                product_map[pid] = {
                    'product_name': mo.product_id.name,
                    'total_qty': 0,
                    'uom': mo.product_uom_id.name,
                    'orders': [],
                }

            # Delivery Date
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

            # 5. Add the REMAINING quantity instead of the MO quantity
            product_map[pid]['total_qty'] += remaining_qty

            # Orders Data
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
                'qty': remaining_qty,  # <-- Pushing the pending inventory quantity here
                'state': mo.state,
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