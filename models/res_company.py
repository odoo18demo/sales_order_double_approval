from odoo import fields, models


class ResCompany(models.Model):
    """ Inheriting res.company model to add custom field """
    _inherit = 'res.company'

    so_double_validation = fields.Boolean(
        string="Sale Order Approval",
        help="Enable this option to require double validation for sale orders. "
             "When enabled, sale orders exceeding a specified minimum amount "
             "will require approval by a sales manager.")
