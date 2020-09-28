# -*- coding: utf-8 -*-
{
    'name': "NexTo Airtable cron",

    'summary': """
        Module for NexTo's Airtable cron jobs.
        """,

    'description': """
        All Airtable cron jobs should be created in this module.
    """,

    'author': "NexTo",
    'website': "http://nex-to.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Administration',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'mail'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/res_config_settings.xml',
        'data/ir_cron_data.xml',
    ],
}
