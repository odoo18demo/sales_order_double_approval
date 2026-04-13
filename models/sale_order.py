from odoo import fields, models
import uuid
import base64

class SaleOrder(models.Model):
    """ Inheriting sale.order to add new state """
    _inherit = 'sale.order'

    state = fields.Selection(selection_add=
                             [('to_approve', 'To Approve'),
                              ('sent',)], ondelete={'to_approve': 'cascade'})
    approval_token = fields.Char(string="Approval Token", readonly=True)

    def button_approve(self):
        """ Method to approve the sale order and change its state to 'sale' """
        self.write({'state': 'draft'})
        return super(SaleOrder, self).action_confirm()

    def _needs_approval(self):
        """ Helper method to check if the sale order needs approval """
        self.ensure_one()
        if not self.company_id.so_double_validation:
            return False

        if not self.env['ir.config_parameter'].sudo().get_param(
                'sales_order_double_approval.so_approval'):
            return False

        min_amount = float(
            self.env['ir.config_parameter'].sudo().get_param(
                'sales_order_double_approval.so_min_amount', default=0))

        if self.amount_total <= min_amount:
            return False

        if self.env.user.has_group('sales_team.group_sale_manager'):
            return False

        return True

    def action_confirm(self):
        """ Override to add double validation logic based on company settings.
        Confirms the sale order if conditions are met, otherwise sets state to
        'to_approve'. """
        for order in self:
            if order._needs_approval():
                # Generate token
                order.approval_token = str(uuid.uuid4())
                order.state = 'to_approve'
                order._send_approval_email()
            else:
                super(SaleOrder, order).action_confirm()
        return True

    def _send_approval_email(self):
        """ Send email to all sales managers """
        template = self.env.ref('sales_order_double_approval.sale_order_approval_email_template')
        managers = self.env['res.users'].search([('groups_id', 'in', self.env.ref('sales_team.group_sale_manager').id)])

        # Generate PDF
        report = self.env.ref('sale.action_report_saleorder')
        pdf_content, _ = report._render_qweb_pdf(self.id)

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': f'Sale Order {self.name}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'sale.order',
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        # Send email with attachment
        template.sudo().send_mail(
            self.id,
            force_send=True,
            email_values={
                'email_to': ','.join([m.email for m in managers if m.email]),
                'attachment_ids': [(6, 0, [attachment.id])]
            }
        )

    def get_approval_url(self, action):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/sale_approval/{self.id}/{self.approval_token}/{action}"

    def action_cancel(self):
        """ Method to cancel the sale order and change state into 'cancel' """
        self.write({'state': 'cancel'})
