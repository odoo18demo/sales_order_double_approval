{
    'name': 'Sales Order Double Approval',
    'version': '18.0.1.0.1',
    'category': 'Sales',
    'summary': """This module helps to set two separate approvals process for a
     sale order to ensure accuracy and compliance.""",
    'description': """This module enables a process where a sale order must be
     reviewed and approved by two separate individuals or departments before it
     is finalized. This is implemented to ensure accuracy, compliance, and 
     reduce the risk of errors and fraud in sales transactions. """,
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com/',
    'depends': ['sales_team','base', 'sale_management','mrp','stock',],
    'data': [
        'data/email_template.xml',
        'report/delivery_note_report.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/crm_team_view_inherit.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_view.xml',
        'views/stock_delivery_note_report.xml',
        'views/templates.xml'
    ],
    'images': [
        'static/description/banner.jpg',
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}