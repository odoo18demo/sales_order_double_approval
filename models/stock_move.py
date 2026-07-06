from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    qty_meter = fields.Float(
        string='Qty (Meter)',
        compute='_compute_qty_meter',
        store=True
    )

    @api.depends('product_uom_qty', 'product_id.product_tmpl_id.prod_length')
    def _compute_qty_meter(self):
        for move in self:
            length = move.product_id.product_tmpl_id.prod_length or 0.0
            # product_uom_qty in stock.move represents the "Demand" quantity
            move.qty_meter = move.product_uom_qty * length