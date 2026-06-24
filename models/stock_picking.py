from odoo import api,fields, models
import base64
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    driver_name = fields.Many2one('fleet.driver', string="Driver")
    driver_mobile = fields.Char(string="Driver Mobile")

    @api.onchange('driver_name')
    def _onchange_driver_name(self):
        if self.driver_name:
            self.driver_mobile = self.driver_name.phone

    @api.onchange('driver_mobile')
    def _onchange_driver_mobile(self):
        if self.driver_name and self.driver_mobile:
            self.driver_name.phone = self.driver_mobile

    truck_plate_no = fields.Char(string="Truck Plate No")
    customer_phone = fields.Char(string="Customer Phone")
    city_code = fields.Char(string="City Code")
    leave_time = fields.Float(string="Leave Time")

    def button_validate(self):
        _logger.warning("CUSTOM BUTTON_VALIDATE CALLED")

        self = self.with_context(
            skip_backorder=True,
            picking_ids_not_to_backorder=self.ids
        )
        return super().button_validate()

    def _log_less_quantities_than_expected(self, *args, **kwargs):
        _logger.warning("BLOCKING EXCEPTION ACTIVITY")
        return False

    def _action_done(self):
        _logger.warning("CUSTOM ACTION_DONE CALLED")
        res = super()._action_done()
        for picking in self:
            try:
                if picking.state == 'done' and picking.sale_id:
                    _logger.warning(
                        "SENDING DELIVERY EMAIL FOR %s",
                        picking.name
                    )
                    picking._send_custom_validation_email()
            except Exception as e:
                _logger.exception(
                    "ERROR SENDING DELIVERY EMAIL: %s",
                    str(e)
                )
        return res
    def _send_custom_validation_email(self):
        self.ensure_one()
        sale = self.sale_id
        if not sale:
            return
        # GENERATE DELIVERY NOTE PDF
        report_action = self.env.ref(
            'sales_order_double_approval.action_report_delivery_note_custom'
        )
        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            report_action.report_name,
            [self.id]
        )
        _logger.warning("PDF GENERATED SUCCESSFULLY")
        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'Delivery_Note_{self.name}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'mimetype': 'application/pdf',
            'res_model': 'stock.picking',
            'res_id': self.id,
        })
        # FINANCIAL MANAGERS
        fin_managers = self.env['financial.team'].search([
            ('active', '=', True)
        ])
        fin_emails = fin_managers.mapped(
            'user_id.partner_id.email'
        )
        # SALESPERSON
        salesperson_email = (
            sale.user_id.partner_id.email
            if sale.user_id
            else False
        )
        # SALES TEAM MANAGER
        manager_email = (
            sale.team_id.user_id.partner_id.email
            if sale.team_id and sale.team_id.user_id
            else False
        )
        # RECIPIENTS
        emails = fin_emails + [
            salesperson_email,
            manager_email
        ]
        emails = list(set([
            email for email in emails if email
        ]))
        if not emails:
            _logger.warning(
                "NO EMAIL RECIPIENTS FOUND"
            )
            return
        email_to = ",".join(emails)
        validator = self.env.user
        # EMAIL BODY
        subject = f"Delivery Validated - {self.name}"
        body = f"""
        <div style="font-family:Arial,sans-serif;">
            <p>
                Delivery Order <strong>{self.name}</strong>
                has been validated successfully.
            </p>
            <table border="0" cellpadding="5">
                <tr>
                    <td><strong>Sale Order</strong></td>
                    <td>{sale.name}</td>
                </tr>
                <tr>
                    <td><strong>Customer</strong></td>
                    <td>{sale.partner_id.name}</td>
                </tr>
                <tr>
                    <td><strong>Validated By</strong></td>
                    <td>{validator.name}</td>
                </tr>
            </table>
            <p>
                The Delivery Note PDF is attached.
            </p>
        </div>
        """
        mail = self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': email_to,
            'attachment_ids': [(4, attachment.id)],
            'author_id': validator.partner_id.id,
            'reply_to': validator.partner_id.email or '',
        })
        mail.send()
