from odoo import models, fields

class FleetDriver(models.Model):
    _name = 'fleet.driver'
    _description = 'Drivers'

    name = fields.Char(string="Driver Name", required=True)
    phone = fields.Char(string="Phone")
    license_no = fields.Char(string="License No")
    active = fields.Boolean(default=True)