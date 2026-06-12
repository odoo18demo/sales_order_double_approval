import base64
import uuid

from odoo import _, fields, models

class SaleOrder(models.Model):
    """ Inheriting sale.order to add new state """
    _inherit = 'sale.order'

    state = fields.Selection(selection_add=
                             [('to_approve', 'To Approve'),
                              ('sent',)], ondelete={'to_approve': 'cascade'})
    approval_token = fields.Char(string="Approval Token", readonly=True)
    approval_stage = fields.Selection([
        ('pending_revisor', 'Pending Revisor Approval'),
        ('pending_manager', 'Pending Manager Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Stage', readonly=True, copy=False)
    requires_approval = fields.Boolean(
        string='Requires Approval',
        compute='_compute_requires_approval',
    )

    def _compute_requires_approval(self):
        for order in self:
            order.requires_approval = order._needs_approval()

    def _needs_approval(self):
        """ Helper method to check if the sale order needs approval """
        self.ensure_one()
        if self.approval_stage == 'approved':
            return False

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

    def _approval_users(self):
        self.ensure_one()
        return self.team_id.user_id, self.team_id.second_approval_id

    def _render_sale_order_pdf(self):
        self.ensure_one()
        pdf_content, _ = self.sudo().env['ir.actions.report']._render_qweb_pdf(
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

    def action_confirm(self):
        """ Override to add double validation logic based on company settings.
        Confirms the sale order if conditions are met, otherwise sets state to
        'to_approve'. """
        return self.action_submit_for_approval()

    def action_submit_for_approval(self):
        """Submit the quotation into the revisor/manager approval workflow."""
        for order in self:
            if order._needs_approval():
                order.write({
                    'approval_token': str(uuid.uuid4()),
                    'approval_stage': 'pending_revisor',
                    'state': 'to_approve',
                })
                order._send_initial_approval_emails()
            else:
                super(SaleOrder, order).action_confirm()
        return True

    def button_approve(self):
        """Approve from the form button according to the logged-in user."""
        for order in self:
            revisor, manager = order._approval_users()
            approval_step = (
                'manager'
                if self.env.user == manager or order.approval_stage == 'pending_manager'
                else 'revisor'
            )
            order._process_approval('approve', approval_step=approval_step)
        return True

    def _send_initial_approval_emails(self):
        """Send approval emails without attaching the PDF to the order chatter."""
        self.ensure_one()
        revisor, manager = self._approval_users()
        attachment = self._create_sale_order_pdf_attachment(link_to_order=False)

        if revisor and revisor.email:
            self._send_approval_email(
                revisor,
                'revisor',
                _('Sale Order %s Requires Revisor Approval') % self.name,
                attachment,
            )

        if manager and manager.email:
            self._send_approval_email(
                manager,
                'manager',
                _('Sale Order %s Submitted for Approval') % self.name,
                attachment,
            )

        self.message_post(
            body=_(
                'Sale Order %(order)s is pending approval. Approval email has '
                'been sent to the revisor and manager.'
            ) % {'order': self.name},
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

    def _send_approval_email(self, user, approval_step, subject, attachment=None):
        self.ensure_one()
        if not user or not user.email:
            return

        approve_url = self.get_approval_url('approve', approval_step)
        reject_url = self.get_approval_url('reject', approval_step)

        body_html = f"""
        <div style="font-family:Arial; font-size:13px;">
            <p>Dear {user.name},</p>
            <p>Sale Order <strong>{self.name}</strong> requires your approval.</p>
            <p>Customer: <strong>{self.partner_id.name}</strong></p>
            <p>Amount: <strong>{self.currency_id.symbol}{self.amount_total:.2f}</strong></p>
            <p>Please take action:</p>
            <p>
                <a href="{approve_url}"><strong>Approve</strong></a>
                &nbsp;&nbsp;&nbsp;
                <a href="{reject_url}"><strong>Reject</strong></a>
            </p>
            <p>Thank you!</p>
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

        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.sudo().send()

    def _send_notification_email(self, user, subject, body, attachment=None):
        self.ensure_one()
        if not user or not user.email:
            return
        mail_values = {
            'subject': subject,
            'email_from': self.company_id.email or self.user_id.email,
            'email_to': user.email,
            'body_html': '<div style="font-family:Arial; font-size:13px;">%s</div>' % body,
        }
        if attachment:
            mail_values['attachment_ids'] = [(6, 0, [attachment.id])]
        self.env['mail.mail'].sudo().create(mail_values).sudo().send()

    def _process_approval(self, action, approval_step):
        self.ensure_one()
        if self.state != 'to_approve':
            return _('Sale Order %s is no longer waiting for approval.') % self.name

        if action == 'reject':
            self.write({
                'state': 'draft',
                'approval_stage': 'rejected',
                'approval_token': False,
            })
            self.message_post(
                body=_('Sale Order %s was sent back for revision.') % self.name,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
            if self.user_id:
                self._send_notification_email(
                    self.user_id,
                    _('Revision Required for Sale Order %s') % self.name,
                    _('<p>Sale Order <strong>%s</strong> was sent back for revision.</p>') % self.name,
                )
            return _('Sale Order %s has been sent back for revision.') % self.name

        if approval_step == 'manager':
            return self._approve_by_manager()

        return self._approve_by_revisor()

    def _approve_by_revisor(self):
        self.ensure_one()
        if self.approval_stage == 'pending_manager':
            return _('Sale Order %s is already waiting for manager approval.') % self.name

        revisor, manager = self._approval_users()
        self.write({'approval_stage': 'pending_manager'})

        if self.user_id:
            self._send_notification_email(
                self.user_id,
                _('First Approval Done for Sale Order %s') % self.name,
                _('<p>First approval is completed for Sale Order <strong>%s</strong>.</p>') % self.name,
            )

        if manager:
            self._send_approval_email(
                manager,
                'manager',
                _('Sale Order %s Requires Manager Approval') % self.name,
            )

        self.message_post(
            body=_('First approval completed by %s. Waiting for manager approval.') %
            (revisor.name if revisor else _('Revisor')),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return _('First approval completed for Sale Order %s.') % self.name

    def _approve_by_manager(self):
        self.ensure_one()
        revisor, manager = self._approval_users()
        attachment = self._create_sale_order_pdf_attachment(link_to_order=True)
        self.write({
            'state': 'draft',
            'approval_stage': 'approved',
            'approval_token': False,
        })
        self.message_post(
            body=_(
                'Manager approval completed. The approved Sale Order PDF has '
                'been attached. You can now send the quotation by email.'
            ),
            attachment_ids=[attachment.id],
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        if self.user_id:
            self._send_notification_email(
                self.user_id,
                _('Sale Order %s Approved') % self.name,
                _('<p>Sale Order <strong>%s</strong> has been approved by the manager.</p>') % self.name,
                attachment,
            )
        if revisor and revisor != self.user_id:
            self._send_notification_email(
                revisor,
                _('Sale Order %s Approved') % self.name,
                _('<p>Sale Order <strong>%s</strong> has been approved by the manager.</p>') % self.name,
                attachment,
            )
        return _('Sale Order %s has been approved.') % self.name

    def get_approval_url(self, action, approval_step='revisor'):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/sale_approval/{self.id}/{self.approval_token}/{approval_step}/{action}"

    def action_cancel(self):
        """ Method to cancel the sale order and change state into 'cancel' """
        self.write({'state': 'cancel', 'approval_token': False})
