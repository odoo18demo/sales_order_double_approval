from odoo import fields, models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    driver_name = fields.Char("Driver Name")
    driver_mobile = fields.Char("Driver Mobile")
    truck_plate_no = fields.Char("Truck Plate No")
    customer_phone = fields.Char("Customer Phone")
    city_code = fields.Char("City Code")
    leave_time = fields.Float(string="Leave Time")