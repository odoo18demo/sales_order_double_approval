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

            if not sale_order or sale_order.is_force_delivered:
                continue

            pid = mo.product_id.id
            sale_lines = sale_order.order_line.filtered(lambda l: l.product_id.id == pid and not l.display_type)
            if not sale_lines:
                continue

            # Group lines by color for the Grid Cards
            color_groups = {}
            for line in sale_lines:
                line_color = ''
                if line.prod_color:
                    line_color = line.prod_color.name
                elif mo.product_id.product_tmpl_id.prod_color:
                    line_color = mo.product_id.product_tmpl_id.prod_color.name

                if line_color not in color_groups:
                    color_groups[line_color] = []
                color_groups[line_color].append(line)

            # Process each color group for the Card, but add each line separately to 'orders'
            for line_color, grouped_lines in color_groups.items():

                product_color_key = f"{pid}_{line_color}"
                so_product_key = f"{sale_order.id}_{product_color_key}"

                if so_product_key in processed_so_lines:
                    continue

                # Filter lines that still have remaining quantity to deliver
                valid_lines = []
                group_remaining_qty = 0
                for l in grouped_lines:
                    rem = l.product_uom_qty - l.qty_delivered
                    if rem > 0:
                        valid_lines.append((l, rem))
                        group_remaining_qty += rem

                if group_remaining_qty <= 0:
                    continue

                processed_so_lines.add(so_product_key)
                productions |= mo

                if sale_order.partner_id:
                    customer = (
                        sale_order.partner_id.display_name
                        or sale_order.partner_id.parent_id.name
                        or sale_order.partner_id.name
                        or '—'
                    )
                else:
                    customer = 'No Customer'

                if product_color_key not in product_map:
                    base_name = mo.product_id.name
                    if line_color and line_color.lower() not in base_name.lower():
                        display_name = f"{base_name} - {line_color}"
                    else:
                        display_name = base_name

                    product_map[product_color_key] = {
                        'product_name': display_name,
                        'default_code': mo.product_id.default_code or '',
                        'total_qty': 0,
                        'uom': mo.product_uom_id.name,
                        'color': line_color,
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

                # Add total remaining quantity of this color group to the Card
                product_map[product_color_key]['total_qty'] += group_remaining_qty

                order_date_str = '—'
                if sale_order.date_order:
                    order_date_str = sale_order.date_order.strftime('%d-%m-%Y')

                # Append EACH individual sale order line separately so "View All Sale Orders" shows every line
                for line, line_rem_qty in valid_lines:
                    product_map[product_color_key]['orders'].append({
                        'mo_name': mo.name or '—',
                        'origin': mo.origin or '—',
                        'customer': customer,
                        'customer_city': (
                            sale_order.partner_id.city
                            or (sale_order.partner_id.parent_id.city if sale_order.partner_id.parent_id else '—')
                            or '—'
                        ),
                        'salesperson': (
                            sale_order.user_id.name
                            if sale_order.user_id
                            else '—'
                        ),
                        'item_name': mo.product_id.name or '—',
                        'color': line_color or '',
                        'delivery_date': delivery_date,
                        'note': html2plaintext(sale_order.display_note) if sale_order.display_note else '',
                        'qty': int(line_rem_qty) if line_rem_qty == int(line_rem_qty) else line_rem_qty,
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
        show_qty_and_details = True

        return request.render(
            'sales_order_double_approval.mrp_screen_template',
            {
                'productions': productions,
                'products': products,
                'products_json': products_json,
                'show_qty_and_details': show_qty_and_details,
            }
        )