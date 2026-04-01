import base64
from odoo import http
from odoo.http import request


class MaintenanceRequestController(http.Controller):

    @http.route('/maintenance-request', type='http', auth='public', csrf=False)
    def maintenance_form(self, **kwargs):
        equipments = request.env['maintenance.equipment'].sudo().search(
            [], order='name asc'
        )
        return request.render(
            'sales_order_double_approval.maintenance_request_template',
            {
                'equipments': equipments,
                'success': False,
                'error': None,
                'values': {},
                'photo_count': 0,
            }
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
                        'photo_count': 0,
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

            # Create the maintenance request
            maintenance_request = request.env['maintenance.request'].sudo().create(vals)

            # ✅ Handle base64 photos sent as hidden inputs
            photo_count = 0
            index = 0
            while True:
                b64_data = kwargs.get('photo_data_%d' % index)
                filename = kwargs.get('photo_name_%d' % index, 'photo_%d.jpg' % index)
                if not b64_data:
                    break
                try:
                    # Strip the data URL prefix: data:image/jpeg;base64,XXXX
                    if ',' in b64_data:
                        b64_data = b64_data.split(',')[1]
                    request.env['ir.attachment'].sudo().create({
                        'name': filename,
                        'type': 'binary',
                        'datas': b64_data,
                        'res_model': 'maintenance.request',
                        'res_id': maintenance_request.id,
                        'mimetype': 'image/jpeg',
                    })
                    photo_count += 1
                except Exception:
                    pass
                index += 1

            return request.render(
                'sales_order_double_approval.maintenance_request_template',
                {
                    'equipments': equipments,
                    'success': True,
                    'error': None,
                    'values': {},
                    'photo_count': photo_count,
                }
            )

        except Exception as e:
            return request.render(
                'sales_order_double_approval.maintenance_request_template',
                {
                    'equipments': equipments,
                    'success': False,
                    'error': 'Something went wrong: %s' % str(e),
                    'values': kwargs,
                    'photo_count': 0,
                }
            )