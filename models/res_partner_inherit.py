from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    company_type = fields.Selection(
        selection=[
            ('person', 'Branch'),
            ('company', 'Company')
        ],
        string='Company Type',
        compute='_compute_company_type',
        inverse='_write_company_type'
    )