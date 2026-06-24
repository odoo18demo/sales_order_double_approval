from odoo import fields,models


class FinancialTeam(models.Model):
    _name = 'financial.team'

    name = fields.Char(required=True,string="Team Name")
    user_id = fields.Many2one(
        'res.users',
        string='Finance Manager',
        domain=lambda self: [('groups_id', 'in', self.env.ref('sales_team.group_sale_manager').id)]
    )
    active = fields.Boolean(default=True)

