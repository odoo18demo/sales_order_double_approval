import base64
import uuid
from odoo import _, fields, models, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Odoo 18 requires explicit positioning for injected selection states
    state = fields.Selection(selection_add=[
        ('draft_approval', 'Approval Draft'),
        ('to_approve', 'Pending Approval'),
    ], ondelete={'draft_approval': 'cascade', 'to_approve': 'cascade'})

    # Set default stage to our custom pre-quotation state
    approval_token = fields.Char(string="Approval Token", readonly=True, copy=False)
    approval_stage = fields.Selection([
        ('draft', 'Draft'),
        ('pending_revisor', 'Pending Revisor Approval'),
        ('pending_manager', 'Pending Manager Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Stage', default='draft', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Enforce that new records start before Odoo's default 'draft'
            if 'state' not in vals:
                vals['state'] = 'draft_approval'
        return super(SaleOrder, self).create(vals_list)

    def _approval_users(self):
        self.ensure_one()
        return self.team_id.user_id, self.team_id.second_approval_id

    def _render_sale_order_pdf(self):
        self.ensure_one()
        # Odoo 18 action report rendering engine execution syntax
        pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'sale.report_saleorder',
            self.ids,
        )
        return base64.b64encode(pdf_content).decode('utf-8')

    def _create_sale_order_pdf_attachment(self, link_to_order=False):
        self.ensure_one()
        values = {
            'name': _('Sale Order %s.pdf') % self.name,
            'type': 'binary',
            'datas': self._render_sale_order_pdf(),
            'mimetype': 'application/pdf',
        }
        if link_to_order:
            values.update({
                'res_model': 'sale.order',
                'res_id': self.id,
            })
        return self.env['ir.attachment'].sudo().create(values)

    def action_submit_for_approval(self):
        for order in self:
            if order.state != 'draft_approval':
                continue
            order.write({
                'approval_token': str(uuid.uuid4()),
                'approval_stage': 'pending_revisor',
                'state': 'to_approve',
            })
            order._send_initial_approval_emails()
        return True

    def _send_initial_approval_emails(self):
        self.ensure_one()
        revisor, manager = self._approval_users()
        # Created without res_id linkage so it remains hidden from chatter at this stage
        attachment = self._create_sale_order_pdf_attachment(link_to_order=False)

        if revisor and revisor.email:
            self._send_approval_email(
                revisor, 'revisor',
                _('Sale Order %s Requires Revisor Approval') % self.name, attachment
            )
        if manager and manager.email:
            self._send_approval_email(
                manager, 'manager',
                _('Sale Order %s Workflow Initialization Notification') % self.name, attachment
            )

    def _send_approval_email(self, user, approval_step, subject, attachment=None):
        self.ensure_one()
        if not user or not user.email:
            return

        approve_url = self.get_approval_url('approve', approval_step)
        reject_url = self.get_approval_url('reject', approval_step)

        body_html = f"""
        <div style="font-family:Arial, sans-serif; font-size:13px;">
            <p>Dear {user.name},</p>
            <p>Sale Order <strong>{self.name}</strong> is awaiting your evaluation stage.</p>
            <p>Customer: <strong>{self.partner_id.name}</strong></p>
            <p>Amount: <strong>{self.currency_id.symbol if self.currency_id else ''}{self.amount_total:.2f}</strong></p>
            <p>Please select an action to process the workflow tracking state:</p>
            <p style="margin-top: 20px;">
                <a href="{approve_url}" style="background-color: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-weight: bold;">Approve</a>
                &nbsp;&nbsp;
                <a href="{reject_url}" style="background-color: #dc3545; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-weight: bold;">Reject / Revision</a>
            </p>
        </div>
        """
        mail_values = {
            'subject': subject,
            'email_from': self.user_id.email or self.company_id.email,
            'email_to': user.email,
            'body_html': body_html,
        }
        if attachment:
            mail_values['attachment_ids'] = [(6, 0, [attachment.id])]

        self.env['mail.mail'].sudo().create(mail_values).send()

    def _send_notification_email(self, user, subject, body, attachment=None):
        self.ensure_one()
        if not user or not user.email:
            return
        mail_values = {
            'subject': subject,
            'email_from': self.company_id.email or self.user_id.email,
            'email_to': user.email,
            'body_html': '<div style="font-family:Arial, sans-serif; font-size:13px;">%s</div>' % body,
        }
        if attachment:
            mail_values['attachment_ids'] = [(6, 0, [attachment.id])]
        self.env['mail.mail'].sudo().create(mail_values).send()

    def _process_approval(self, action, approval_step):
        self.ensure_one()
        if self.state != 'to_approve':
            return _('Sale Order %s is not currently awaiting verification.') % self.name

        if action == 'reject':
            self.write({
                'state': 'draft_approval',
                'approval_stage': 'rejected',
                'approval_token': False,
            })
            if self.user_id:
                self._send_notification_email(
                    self.user_id,
                    _('Revision Required for Sale Order %s') % self.name,
                    _('<p>Sale Order <strong>%s</strong> was rejected and reverted back to Draft Approval.</p>') % self.name
                )
            return _('Sale Order %s has been pushed back for corrections.') % self.name

        if approval_step == 'manager':
            return self._approve_by_manager()

        return self._approve_by_revisor()

    def _approve_by_revisor(self):
        self.ensure_one()
        if self.approval_stage == 'pending_manager':
            return _('Sale Order %s is already pending manager operational approval.') % self.name

        revisor, manager = self._approval_users()
        self.write({'approval_stage': 'pending_manager'})

        if self.user_id:
            self._send_notification_email(
                self.user_id,
                _('Sale Order %s Confirmed by Revisor') % self.name,
                _('<p>Sale Order <strong>%s</strong> has been confirmed by the Revisor.</p>') % self.name
            )

        # Generate a clean, updated attachment reflecting changes (if any) made by Revisor
        manager_attachment = self._create_sale_order_pdf_attachment(link_to_order=False)
        if manager:
            self._send_approval_email(
                manager, 'manager',
                _('Second Approval Stage Needed: Sale Order %s') % self.name, manager_attachment
            )

        return _('First stage verification completed for Sale Order %s.') % self.name

    def _approve_by_manager(self):
        self.ensure_one()
        revisor, manager = self._approval_users()

        # Link to the order here explicitly so Odoo registers it under this record's attachment pool
        final_attachment = self._create_sale_order_pdf_attachment(link_to_order=True)

        # Shift to Native Odoo 'draft' state (Quotation stage)
        self.write({
            'state': 'draft',
            'approval_stage': 'approved',
            'approval_token': False,
        })

        # Post onto chatter so it displays visually for the sales agent
        self.message_post(
            body=_('Manager approval achieved. The finalized Sale Order document has been compiled and logged.'),
            attachment_ids=[final_attachment.id],
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        success_msg = _(
            '<p>Sale Order <strong>%s</strong> was fully approved by the manager and is ready for customer dispatch.</p>') % self.name

        if self.user_id:
            self._send_notification_email(self.user_id, _('Sale Order %s Approved') % self.name, success_msg,
                                          final_attachment)
        if revisor and revisor != self.user_id:
            self._send_notification_email(revisor, _('Sale Order %s Approved') % self.name, success_msg,
                                          final_attachment)

        return _('Sale Order %s successfully shifted to Odoo standard Quotation pipeline.') % self.name

    def get_approval_url(self, action, approval_step='revisor'):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/sale_approval/{self.id}/{self.approval_token}/{approval_step}/{action}"