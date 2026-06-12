from odoo import models, fields

class CrmTeam(models.Model):
    _inherit = 'crm.team'

    second_approval_id = fields.Many2one(
        'res.users',
        string='Manager'
    )
    sales_manager_ids = fields.Many2many(
        'res.users',
        compute='_compute_sales_manager_ids'
    )

    def _compute_sales_manager_ids(self):
        group = self.env.ref('sales_team.group_sale_manager')
        users = group.users
        for rec in self:
            rec.sales_manager_ids = users
