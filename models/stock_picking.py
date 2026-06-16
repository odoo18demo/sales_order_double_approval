from odoo import fields, models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    driver_name = fields.Many2one('fleet.driver',string="Driver")
    driver_mobile = fields.Char(related='driver_name.phone', store=True, string="Driver Mobile")
    truck_plate_no = fields.Char("Truck Plate No")
    customer_phone = fields.Char(related='partner_id.phone', store=True, string="Customer Phone")
    city_code = fields.Char("City Code")
    leave_time = fields.Float(string="Leave Time")