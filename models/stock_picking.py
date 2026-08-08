from odoo import api,fields, models
import base64
import logging
from odoo.exceptions import UserError
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
    customer_phone = fields.Char(
        string="Customer Phone",
        related="partner_id.phone",
        readonly=False  # Set to True if you want to lock it!
    )
    city_code = fields.Char(string="City Code")
    # leave_time = fields.Float(string="Leave Time")
    leave_datetime = fields.Datetime(
        string="Leave Time",
        default=fields.Datetime.now
    )
    def button_validate(self):
        _logger.warning("CUSTOM BUTTON_VALIDATE CALLED")

        # ==============================================================
        # NEW LOGIC: Block extra quantities and unapproved new products
        # ==============================================================
        for picking in self:
            # Only enforce this on Deliveries linked to a Sale Order
            if picking.sale_id:
                for move in picking.move_ids:
                    # 1. Block products that were added manually by the warehouse
                    if not move.sale_line_id:
                        raise UserError(
                            f"Error: You cannot add new products ({move.product_id.display_name}) to a Delivery that were not on the approved Sale Order!")

        #             # 2. Block delivering more than the demanded quantity
        #             if move.quantity > move.product_uom_qty:
        #                 raise UserError(
        #                     f"Error: You are trying to deliver {move.quantity} of {move.product_id.display_name}, but only {move.product_uom_qty} was ordered!")
        # # ==============================================================

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

        # ==============================================================
        # 1. GENERATE DELIVERY NOTE PDF
        # ==============================================================
        delivery_pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'stock.report_deliveryslip',
            [self.id]
        )
        delivery_attachment = self.env['ir.attachment'].sudo().create({
            'name': f'Delivery_Note_{self.name}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(delivery_pdf_content),
            'mimetype': 'application/pdf',
            'res_model': 'stock.picking',
            'res_id': self.id,
        })

        # ==============================================================
        # 2. GENERATE SALE ORDER PDF (Using Custom Layout)
        # ==============================================================
        so_pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'united_custom_layout.report_united_sale_order_document',
            [sale.id]
        )
        so_attachment = self.env['ir.attachment'].sudo().create({
            'name': f'Sale_Order_{sale.name}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(so_pdf_content),
            'mimetype': 'application/pdf',
            'res_model': 'sale.order',
            'res_id': sale.id,
        })

        # ==============================================================
        # 3. GATHER EMAIL RECIPIENTS
        # ==============================================================
        # Financial Managers
        fin_managers = self.env['financial.team'].search([('active', '=', True)])
        fin_emails = fin_managers.mapped('user_id.partner_id.email')

        # Salesperson (The person who created the order)
        salesperson_email = sale.user_id.partner_id.email if sale.user_id else False

        # Sales Team Manager
        manager_email = sale.team_id.user_id.partner_id.email if sale.team_id and sale.team_id.user_id else False

        # Combine all emails into one list
        emails = fin_emails + [salesperson_email, manager_email]

        # Remove empty values (if no email exists) and remove duplicates
        valid_emails = list(set([email for email in emails if email]))

        if not valid_emails:
            _logger.warning("NO EMAIL RECIPIENTS FOUND")
            return

        email_to = ",".join(valid_emails)
        validator = self.env.user

        # ==============================================================
        # 4. CREATE THE EMAIL MESSAGE
        # ==============================================================
        subject = f"Delivery Validated - {sale.name}"
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
                Please find the Delivery Note and the original Sale Order attached below.
            </p>
        </div>
        """

        # ==============================================================
        # 5. SEND THE EMAIL WITH BOTH ATTACHMENTS
        # ==============================================================
        mail = self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': email_to,
            # Attach both the Delivery Slip and the Sale Order!
            'attachment_ids': [(4, delivery_attachment.id), (4, so_attachment.id)],
            'author_id': validator.partner_id.id,
            'reply_to': validator.partner_id.email or '',
        })
        mail.send()
        _logger.warning("EMAIL SENT SUCCESSFULLY WITH BOTH PDFS")

    @api.onchange('sale_id')
    def _onchange_sale_id_populate_remaining(self):
        """
        When a user manually selects a Sale Order on a Draft picking,
        auto-populate remaining quantities, customer, and link the smart button.
        """
        if not self.sale_id or self.state != 'draft':
            return

        procurement_group = self.sale_id.procurement_group_id

        # 1. Update Customer Name & Origin
        self.partner_id = self.sale_id.partner_shipping_id.id or self.sale_id.partner_id.id
        self.origin = self.sale_id.name

        # 2. Populate Operations with remaining products
        self.move_ids_without_package = [(5, 0, 0)]
        new_lines = []
        for line in self.sale_id.order_line:
            if line.display_type or line.product_id.type == 'service':
                continue

            remaining_qty = line.product_uom_qty - line.qty_delivered
            if remaining_qty > 0:
                new_lines.append((0, 0, {
                    'name': line.name or line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': remaining_qty,
                    'product_uom': line.product_uom.id,
                    'location_id': self.location_id.id or self.picking_type_id.default_location_src_id.id,
                    'location_dest_id': self.location_dest_id.id or self.picking_type_id.default_location_dest_id.id,
                    'sale_line_id': line.id,
                    'company_id': self.company_id.id,
                    'group_id': procurement_group.id,
                    # === ADD THESE 3 CRITICAL FIELDS TO STABILIZE THE VIRTUAL RECORD ===
                    'picking_type_id': self.picking_type_id.id,
                    'procure_method': 'make_to_stock',
                    'state': 'draft',
                }))

        if new_lines:
            self.move_ids_without_package = new_lines

    @api.model_create_multi
    def create(self, vals_list):
        """ Intercept creation to force the Sales Order Line links """
        pickings = super().create(vals_list)
        for picking in pickings:
            if picking.sale_id:
                picking._force_sale_line_links()
        return pickings

    def write(self, vals):
        """ Intercept saves to force the Sales Order Line links """
        res = super().write(vals)
        for picking in self:
            if picking.sale_id:
                picking._force_sale_line_links()
        return res

    def _force_sale_line_links(self):
        """
        Backend helper to securely connect the stock move to the original SO line.
        This prevents Odoo from creating duplicate 0-demand lines!
        """
        for move in self.move_ids:
            # If the move lost its connection to the order line...
            if not move.sale_line_id and self.sale_id:
                # Find the matching product on the Sales Order
                matching_line = self.sale_id.order_line.filtered(
                    lambda l: l.product_id.id == move.product_id.id
                )
                if matching_line:
                    # Force the connection in the database!
                    move.sale_line_id = matching_line[0].id

    # ADD THIS: The manual toggle for the warehouse team
    is_force_delivered = fields.Boolean(string="Force Fully Delivered", default=False, copy=False)

    def action_cancel(self):
        # 1. Bypass check if the context flag is passed (e.g., from wizard "Cancel Only Delivery" button)
        if self.env.context.get('skip_deep_cancel_check'):
            return super(StockPicking, self).action_cancel()

        for picking in self:
            # If the picking is already done, let standard Odoo handle it (normally raises an error)
            if picking.state == 'done':
                continue

            # If there is a linked Sale Order
            if picking.sale_id:
                # Check if this Sale Order has ANY OTHER deliveries that are already 'done'
                other_done_deliveries = picking.sale_id.picking_ids.filtered(
                    lambda p: p.state == 'done' and p.id != picking.id
                )

                # If NO other deliveries are done, show the Safety Net Wizard
                if not other_done_deliveries:
                    return {
                        'name': 'Cancel Workflow Confirmation',
                        'type': 'ir.actions.act_window',
                        'res_model': 'picking.deep.cancel.wizard',
                        'view_mode': 'form',
                        'target': 'new',
                        'context': {'default_picking_id': picking.id}
                    }
                # If there ARE other done deliveries, it skips the IF block and does normal cancel below

        # 2. If no Sale Order, or SO has other done deliveries, do normal Odoo cancel
        return super(StockPicking, self).action_cancel()

    delivery_badge_status = fields.Selection([
        ('pending', 'Pending Delivery'),
        ('partial', 'Partially Delivered'),
        ('full', 'Fully Delivered'),
        ('cancelled', 'Cancelled')
    ], string="Delivery Status", compute="_compute_delivery_badge_status", store=False)

    @api.depends('sale_id.delivery_badge_status', 'state', 'is_force_delivered')
    def _compute_delivery_badge_status(self):
        for picking in self:
            # 1. ALWAYS check if the delivery itself is cancelled FIRST
            if picking.state == 'cancel':
                picking.delivery_badge_status = 'cancelled'

            # 2. If linked to a Sale Order, perfectly mirror the SO's overall status
            elif picking.sale_id:
                picking.delivery_badge_status = picking.sale_id.delivery_badge_status

            # 3. If NO Sale Order exists (Standalone Delivery)
            else:
                # If manually forced or officially validated as done
                if picking.is_force_delivered or picking.state == 'done':
                    picking.delivery_badge_status = 'full'
                # If still in draft, waiting, or ready
                else:
                    picking.delivery_badge_status = 'pending'

    def action_set_to_draft(self):
        for picking in self:
            if picking.state == 'cancel':
                # 1. Reset the move lines (Detailed Operations)
                picking.move_line_ids.write({'state': 'draft'})

                # 2. Reset the moves (Operations)
                picking.move_ids.write({'state': 'draft'})

                # 3. Reset the Picking itself
                picking.write({'state': 'draft'})

    @api.onchange('quantity')
    def _onchange_quantity_sync_demand(self):
        """
        If there is NO linked Sale Order (standalone delivery),
        automatically make the Demand (product_uom_qty) equal
        to whatever quantity is being delivered.
    """
        for move in self:
            # Check if the parent picking has NO sale_id
            if move.picking_id and not move.picking_id.sale_id:
                move.product_uom_qty = move.quantity