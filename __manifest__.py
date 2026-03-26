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
    'depends': ['base', 'sale_management'],
    'data': [
        'data/email_template.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml'
    ],
    'images': [
        'static/description/banner.jpg',
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}