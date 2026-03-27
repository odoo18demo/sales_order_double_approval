from odoo import http
from odoo.http import request


class MaintenanceRequestController(http.Controller):

    @http.route('/maintenance-request', type='http', auth='public', csrf=False)
    def maintenance_form(self, **kwargs):
        # Get all equipment for dropdown
        equipments = request.env['maintenance.equipment'].sudo().search(
            [], order='name asc'
        )
        return request.render(
            'sales_order_double_approval.maintenance_request_template',
            {'equipments': equipments, 'success': False, 'error': None}
        )

    @http.route('/maintenance-request/submit', type='http', auth='public',
                methods=['POST'], csrf=False)
    def maintenance_submit(self, **kwargs):
        equipments = request.env['maintenance.equipment'].sudo().search(
            [], order='name asc'
        )
        try:
            name = kwargs.get('name', '').strip()
            description = kwargs.get('description', '').strip()
            equipment_id = kwargs.get('equipment_id')
            priority = kwargs.get('priority', '0')
            maintenance_type = kwargs.get('maintenance_type', 'corrective')

            if not name:
                return request.render(
                    'sales_order_double_approval.maintenance_request_template',
                    {
                        'equipments': equipments,
                        'success': False,
                        'error': 'Request name is required.',
                        'values': kwargs,
                    }
                )

            vals = {
                'name': name,
                'description': description,
                'priority': priority,
                'maintenance_type': maintenance_type,
            }
            if equipment_id:
                vals['equipment_id'] = int(equipment_id)

            request.env['maintenance.request'].sudo().create(vals)

            return request.render(
                'sales_order_double_approval.maintenance_request_template',
                {'equipments': equipments, 'success': True, 'error': None}
            )

        except Exception as e:
            return request.render(
                'sales_order_double_approval.maintenance_request_template',
                {
                    'equipments': equipments,
                    'success': False,
                    'error': 'Something went wrong. Please try again.',
                    'values': kwargs,
                }
            )