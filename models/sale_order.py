import base64
import uuid
from odoo import _, fields, models, api
from odoo.http import request
from odoo.exceptions import UserError
from odoo import http


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    display_note = fields.Text(string='Note')
    # Odoo 18 requires explicit positioning for injected selection states
    state = fields.Selection(
        selection_add=[
            ('draft_approval', 'Draft'),
            ('to_approve', 'Pending Approval'),
            ('draft',),
        ],
        default='draft_approval',
        ondelete={
            'draft_approval': 'cascade',
            'to_approve': 'cascade',
        }
    )

    # Set default stage to our custom pre-quotation state
    approval_token = fields.Char(string="Approval Token", readonly=True, copy=False)
    approval_stage = fields.Selection([
        ('draft', 'Draft'),
        ('pending_revisor', 'Pending Revisor Approval'),
        ('pending_manager', 'Pending Manager Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Stage', default='draft', readonly=True, copy=False)

    def _approval_users(self):
        self.ensure_one()
        return self.team_id.user_id, self.team_id.second_approval_id

    def _render_sale_order_pdf(self):
        self.ensure_one()
        # Pointing to the new United Custom Layout
        pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'united_custom_layout.report_united_sale_order_document',
            self.ids,
        )
        return base64.b64encode(pdf_content).decode('utf-8')

    def _create_sale_order_pdf_attachment(self, link_to_order=False):
        self.ensure_one()

        # 1. If the order is fully confirmed
        if self.state == 'sale':
            file_name = _('Sales Order - %s.pdf') % self.name

        # 2. If it is in your custom double-approval process
        elif self.state in ['draft_approval', 'to_approve']:
            file_name = _('Draft - %s.pdf') % self.name

        # 3. If it is standard Odoo draft or sent
        else:
            file_name = _('Quotation - %s.pdf') % self.name

        values = {
            'name': file_name,
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
                _('Sale Order %s Requires Revisor Approval') % self.name,
                attachment=attachment,
                sender_user=self.user_id # Force sender: Salesperson
            )
        if manager and manager.email:
            self._send_approval_email(
                manager, 'manager',
                _('Sale Order %s Workflow Initialization Notification') % self.name,
                attachment=attachment,
                sender_user=self.user_id # Force sender: Salesperson
            )

    def _send_approval_email(self, user, approval_step, subject, attachment=None, sender_user=None):
        self.ensure_one()
        if not user or not user.email:
            return

        approve_url = self.get_approval_url('approve', approval_step)
        reject_url = self.get_approval_url('reject', approval_step)

        # ✅ FORCE EXACT SENDER EMAIL
        if sender_user and sender_user.email:
            email_from = sender_user.email_formatted or sender_user.email
        else:
            email_from = self._get_approval_sender()

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
                <a href="{reject_url}" style="background-color: #dc3545; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-weight: bold;">Reject</a>
            </p>
        </div>
        """

        mail_values = {
            'subject': subject,
            'email_from': email_from,
            'email_to': user.email,
            'body_html': body_html,
        }

        if attachment:
            mail_values['attachment_ids'] = [(6, 0, [attachment.id])]

        self.env['mail.mail'].sudo().create(mail_values).send()

    def _send_notification_email(self, user, subject, body, attachment=None, sender_user=None):
        self.ensure_one()
        if not user or not user.email:
            return

        # ✅ FORCE EXACT SENDER EMAIL
        if sender_user and sender_user.email:
            email_from = sender_user.email_formatted or sender_user.email
        else:
            email_from = self._get_approval_sender()

        mail_values = {
            'subject': subject,
            'email_from': email_from,
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

        revisor, manager = self._approval_users()
        current_approver = manager if approval_step == 'manager' else revisor

        if action == 'reject':
            self.write({
                'state': 'cancel',
                'approval_stage': 'rejected',
                'approval_token': False,
            })
            if self.user_id:
                self._send_notification_email(
                    self.user_id,
                    _('Sale Order %s Rejected and Cancelled') % self.name,
                    _('<p>Sale Order <strong>%s</strong> was rejected by the approver and has been cancelled.</p>') % self.name,
                    sender_user=current_approver # Force sender: Whoever rejected it
                )
            return _('Sale Order %s has been permanently cancelled.') % self.name

        if approval_step == 'manager':
            return self._approve_by_manager()

        return self._approve_by_revisor()

    def _approve_by_revisor(self):
        self.ensure_one()
        if self.approval_stage == 'pending_manager':
            return _('Sale Order %s is already pending manager operational approval.') % self.name

        revisor, manager = self._approval_users()
        self.write({'approval_stage': 'pending_manager'})
        self.message_post(
            body=_('Quotation approved by Revisor: %s') % revisor.name,
            subtype_xmlid='mail.mt_note',
        )

        if self.user_id:
            self._send_notification_email(
                self.user_id,
                _('Quotation Approved By Revisor'),
                _(
                    '<p>Quotation Number: <strong>%s</strong></p>'
                    '<p>The Revisor has approved this quotation.</p>'
                    '<p>Waiting for Manager approval.</p>'
                ) % self.name,
                sender_user=revisor # Force sender: Revisor
            )

        manager_attachment = self._create_sale_order_pdf_attachment(link_to_order=False)
        if manager:
            self._send_approval_email(
                manager, 'manager',
                _('Second Approval Stage Needed: Sale Order %s') % self.name,
                attachment=manager_attachment,
                sender_user=revisor # Force sender: Revisor
            )

        return _('First stage verification completed for Sale Order %s.') % self.name

    def _approve_by_manager(self):
        self.ensure_one()
        revisor, manager = self._approval_users()

        old_attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'application/pdf'),
            ('name', 'ilike', self.name)
        ])
        if old_attachments:
            old_attachments.unlink()

        self.write({
            'state': 'draft',
            'approval_stage': 'approved',
            'approval_token': False,
        })

        final_attachment = self._create_sale_order_pdf_attachment(link_to_order=True)

        self.message_post(
            body=_('Quotation approved by Manager: %s') % manager.name,
            attachment_ids=[final_attachment.id],
            subtype_xmlid='mail.mt_note',
        )

        success_msg = _(
            '<p>Quotation Number: <strong>%s</strong></p>'
            '<p>Customer: <strong>%s</strong></p>'
            '<p>Total Amount: <strong>%s %.2f</strong></p>'
            '<p>The quotation has been approved by the Manager.</p>'
            '<p>You may now send it to the customer.</p>'
        ) % (self.name, self.partner_id.name, self.currency_id.symbol, self.amount_total,)

        if self.user_id:
            self._send_notification_email(
                self.user_id, _('Sale Order %s Approved') % self.name, success_msg,
                attachment=final_attachment,
                sender_user=manager # Force sender: Manager
            )
        if revisor and revisor != self.user_id:
            self._send_notification_email(
                revisor, _('Sale Order %s Approved') % self.name, success_msg,
                attachment=final_attachment,
                sender_user=manager # Force sender: Manager
            )

        return _('Sale Order %s successfully shifted to Odoo standard Quotation pipeline.') % self.name

    def get_approval_url(self, action, approval_step='revisor'):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/sale_approval/{self.id}/{self.approval_token}/{approval_step}/{action}"

    def button_approve(self):
        for order in self:
            revisor, manager = order._approval_users()
            current_user = self.env.user

            if current_user == manager:
                # Manager can approve at any point — acts as final approval,
                # skipping the revisor stage if they haven't approved yet
                approval_step = 'manager'
            elif current_user == revisor:
                if order.approval_stage != 'pending_revisor':
                    raise UserError(_('You have already approved this stage.'))
                approval_step = 'revisor'
            else:
                raise UserError(_('You are not authorized to approve this Sale Order.'))
            order._process_approval('approve', approval_step)

    def _validate_order(self):
        """
        Odoo calls this method from the Portal when a customer signs.
        We want to intercept it and block the confirmation ONLY if the
        person signing is the external customer on the portal.
        """
        # Check if this is happening during a web request
        if request and request.session:

            # If the user is Public (not logged in as an internal Odoo user)
            # Or if they are purely a Portal User
            if request.env.user._is_public() or request.env.user.share:
                # STOP! Do not run the core Odoo validation.
                # Just return False to keep it as a Quotation Sent.
                return False

        # If it's a real Salesperson clicking confirm, let Odoo do its normal job
        return super(SaleOrder, self)._validate_order()

    def action_draft(self):
        # Run standard Odoo 'Set to Quotation' logic first
        res = super(SaleOrder, self).action_draft()

        # Force the state back to your custom starting line
        for order in self:
            order.write({
                'state': 'draft_approval',
                'approval_stage': 'draft',
                'approval_token': False,
            })
        return res

    is_revisor = fields.Boolean(compute="_compute_approvers")
    is_manager = fields.Boolean(compute="_compute_approvers")

    @api.depends('team_id', 'team_id.user_id', 'team_id.second_approval_id')
    def _compute_approvers(self):
        for rec in self:
            user = self.env.user
            rec.is_revisor = (rec.team_id.user_id == user)
            rec.is_manager = (rec.team_id.second_approval_id == user)

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for order in self:
            order._send_confirmation_email_to_manager()
        return res

    def _send_confirmation_email_to_manager(self):
        self.ensure_one()
        revisor, manager = self._approval_users()
        if not manager or not manager.email:
            return

        attachment = self._create_sale_order_pdf_attachment(link_to_order=True)

        body = _(
            '<p>Sale Order <strong>%s</strong> has been confirmed.</p>'
            '<p>Customer: <strong>%s</strong></p>'
            '<p>Total Amount: <strong>%s %.2f</strong></p>'
        ) % (self.name, self.partner_id.name, self.currency_id.symbol or '', self.amount_total)

        self._send_notification_email(
            manager,
            _('Sale Order %s Confirmed') % self.name,
            body,
            attachment=attachment,
            sender_user=self.user_id,  # Force sender: Salesperson
        )

    def action_cancel(self):
        for order in self:
            if order.state == 'draft_approval':
                order.write({
                    'state': 'cancel',
                    'approval_stage': 'rejected',
                    'approval_token': False,
                })
        return True

    def _get_approval_sender(self):
        self.ensure_one()

        user = self.env.user

        # If real internal user (Revisor/Manager approving in UI)
        if user and not user._is_public():
            return user.email_formatted or user.email

        # fallback chain
        return (
            self.company_id.email
            or self.env.ref('base.user_admin').email
            or self.user_id.email
        )

    # Add this with your other fields
    is_salesperson = fields.Boolean(compute='_compute_is_salesperson')

    @api.depends('user_id')
    def _compute_is_salesperson(self):
        for rec in self:
            # Returns True if the logged-in user is the Salesperson
            rec.is_salesperson = (rec.user_id == self.env.user)

    is_current_approver = fields.Boolean(compute='_compute_is_current_approver')

    @api.depends('state', 'approval_stage', 'is_revisor', 'is_manager')
    def _compute_is_current_approver(self):
        for rec in self:
            if rec.state == 'to_approve':
                if rec.approval_stage == 'pending_revisor' and rec.is_revisor:
                    rec.is_current_approver = True
                elif rec.approval_stage == 'pending_manager' and rec.is_manager:
                    rec.is_current_approver = True
                else:
                    rec.is_current_approver = False
            else:
                rec.is_current_approver = False


# CREATE THIS NEW CLASS at the bottom of your Python file
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'order_id' in vals:
                order = self.env['sale.order'].browse(vals['order_id'])
                # Block adding new lines unless it's in the initial draft stage
                if order.state not in ['draft_approval']:
                    raise UserError(
                        _("Security restriction: You cannot add new products to an order that is currently pending approval or already approved."))
        return super(SaleOrderLine, self).create(vals_list)

    def unlink(self):
        for line in self:
            # Block deleting lines unless it's in the initial draft stage
            if line.order_id.state not in ['draft_approval']:
                raise UserError(
                    _("Security restriction: You cannot delete products from an order that is currently pending approval or already approved."))
        return super(SaleOrderLine, self).unlink()