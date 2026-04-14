# Add this at the top of your models.py
import base64
import uuid  # already there
from odoo import fields, models

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

        if self.env.user == self.team_id.user_id:
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
        """Send approval email directly to managers without logging links in chatter"""
        leader = self.team_id.user_id

        if not leader or not leader.email:
            return

        email_to = leader.email

        approve_url = self.get_approval_url('approve')
        reject_url = self.get_approval_url('reject')

        # Generate PDF attachment
        pdf_content, _ = self.sudo().env['ir.actions.report']._render_qweb_pdf(
            'sale.report_saleorder', self.ids
        )
        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'Sale Order {self.name}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_content).decode('utf-8'),
            'res_model': 'sale.order',
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        body_html = f"""
        <div style="font-family:Arial; font-size:13px;">
            <p>Dear ${self.team_id.user_id.name},</p>
            <p>Sale Order <strong>{self.name}</strong> requires your approval.</p>
            <p>Customer: <strong>{self.partner_id.name}</strong></p>
            <p>Amount: <strong>{self.currency_id.symbol}{self.amount_total:.2f}</strong></p>
            <p>Please take action:</p>
            <p>
                ✅ <a href="{approve_url}"><strong>Approve</strong></a>
                &nbsp;&nbsp;&nbsp;
                ❌ <a href="{reject_url}"><strong>Reject</strong></a>
            </p>
            <p>Thank you!</p>
        </div>
        """

        # ✅ Create mail.mail directly — NOT linked to res_id
        # So it will NEVER appear in chatter
        mail = self.env['mail.mail'].sudo().create({
            'subject': f'Sale Order {self.name} Requires Approval',
            'email_from': self.company_id.email or self.env.user.email,
            'email_to': email_to,
            'body_html': body_html,
            'attachment_ids': [(6, 0, [attachment.id])],
            # ✅ No res_id / model = not linked to record = not shown in chatter
        })
        mail.sudo().send()

        # ✅ Post a clean chatter message WITHOUT approve/reject links
        self.message_post(
            body=f'⏳ Sale Order {self.name} is pending approval. '
                 f'Approval email has been sent to Sales Managers.',
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

    def get_approval_url(self, action):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/sale_approval/{self.id}/{self.approval_token}/{action}"

    def action_cancel(self):
        """ Method to cancel the sale order and change state into 'cancel' """
        self.write({'state': 'cancel'})
