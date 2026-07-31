from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


# ==============================================================
# 1. NEW WIZARD: The Safety Net Pop-up
# ==============================================================
class PickingDeepCancelWizard(models.TransientModel):
    _name = 'picking.deep.cancel.wizard'
    _description = 'Deep Cancel Confirmation'

    picking_id = fields.Many2one('stock.picking', string="Delivery Order")
    warning_text = fields.Text(
        default="This Delivery is linked to a Sale Order.\n\n"
                "Do you want to completely TEAR DOWN the manufactured products, "
                "cancel the Sale Order, and send it back to Draft?\n\n"
                "Or do you just want to cancel this specific delivery document normally?"
    )

    def action_cancel_everything(self):
        self.ensure_one()
        sale_order = self.picking_id.sale_id
        if not sale_order:
            return True

        # STEP A: Auto-Unbuild Manufacturing Orders
        done_mos = self.env['mrp.production'].sudo().search([
            ('origin', '=', sale_order.name),
            ('state', '=', 'done')
        ])

        for mo in done_mos:
            try:
                unbuild = self.env['mrp.unbuild'].sudo().create({
                    'mo_id': mo.id,
                    'product_id': mo.product_id.id,
                    'product_qty': mo.product_qty,
                    'product_uom_id': mo.product_uom_id.id,
                    'location_id': mo.location_dest_id.id,
                    'location_dest_id': mo.location_src_id.id,
                    'company_id': mo.company_id.id,
                })
                unbuild.action_validate()
                _logger.warning("Successfully auto-unbuilt MO: %s", mo.name)
            except Exception as e:
                _logger.warning("Could not auto-unbuild MO %s: %s", mo.name, str(e))

        # STEP B: Safely cancel THIS delivery first so the Sale Order doesn't block us!
        if self.picking_id.state != 'cancel':
            # The context flag stops the pop-up from looping endlessly
            self.picking_id.with_context(skip_deep_cancel_check=True).action_cancel()

        # STEP C: Cancel the Sale Order
        if sale_order.state != 'cancel':
            # Use disable_cancel_warning to bypass Odoo's native confirmation pop-ups
            sale_order.with_context(disable_cancel_warning=True).action_cancel()

        # STEP D: Set Sale Order back to Draft
        if sale_order.state == 'cancel':
            sale_order.action_draft()

        return True

    def action_cancel_only_delivery(self):
        self.ensure_one()
        # Just do standard Odoo cancel on this picking by passing a secret context flag!
        self.picking_id.with_context(skip_deep_cancel_check=True).action_cancel()
        return True