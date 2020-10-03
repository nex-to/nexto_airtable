# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, timezone
import requests
import json
import logging


class AirtableDeliveryItemPrediction:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.product_id = kwargs.get('product_id')
        self.agency_size = kwargs.get('agency_size')
        self.quantity = kwargs.get('quantity')


class AirtableDeliveryItemPredictions:
    def __init__(self):
        self._predictions = []

    def __len__(self):
        return len(self._predictions)

    def add_prediction(self, prediction: AirtableDeliveryItemPrediction):
        self._predictions.append(prediction)

    def get_prediction(self, product_id: str, agency_size: str):
        for prediction in self._predictions:
            if prediction.product_id == product_id and prediction.agency_size == agency_size:
                return prediction.quantity
        return None


class NexToAirtable(models.Model):
    _name = 'nexto.airtable'
    _description = 'Model for Airtable API interaction.'

    api_token = fields.Char('API Token', required=True)
    base_url = fields.Char('Base URL', required=True)
    api_version = fields.Char('API Version', required=True)
    airtable_base = fields.Char('Airtable Base ID', required=True)
    cron_user_id = fields.Char('Cron User ID', required=True)

    def _get_headers(self):
        headers = {
            'Authorization': 'Bearer ' + self.env['generic.crypto.param'].get_param('nexto.airtable.api_token')
        }
        return headers

    def _min_config(self):
        bln_min_config = True
        _logging = logging.getLogger(__name__)

        if self.env['ir.config_parameter'].get_param('nexto.airtable.base_url') is None:
            _logging.warning('Base URL is not set.')
            bln_min_config = False

        if self.env['ir.config_parameter'].get_param('nexto.airtable.api_version') is None:
            _logging.warning('API Version is not set.')
            bln_min_config = False

        if self.env['ir.config_parameter'].get_param('nexto.airtable.airtable_base') is None:
            _logging.warning('Airtable Base ID is not set.')
            bln_min_config = False

        if self.env['generic.crypto.param'].get_param('nexto.airtable.api_token') is None:
            _logging.warning('Airtable API Token is not set.')
            bln_min_config = False

        if self.env['ir.config_parameter'].get_param('nexto.airtable.cron_user_id') is None:
            _logging.warning('Airtable cron User ID is not set.')
            bln_min_config = False

        return bln_min_config

    def _insert_delivery_items_on_delivery_request(self, distributor_id=None):
        if self._min_config() is False:
            return

        if distributor_id is None:
            _logging = logging.getLogger(__name__)
            _logging.warning('Missing argument distributor_id.')
            return

        base_url = self.env['ir.config_parameter'].get_param('nexto.airtable.base_url')
        api_version = self.env['ir.config_parameter'].get_param('nexto.airtable.api_version')
        airtable_base = self.env['ir.config_parameter'].get_param('nexto.airtable.airtable_base')
        cron_user_id = self.env['ir.config_parameter'].get_param('nexto.airtable.cron_user_id')

        # GET ALL RECORDS FROM DeliveryItemPredictions TABLE TO REDUCE THE CUMULATIVE NUMBER OF API REQUESTS.  SINCE THERE AREN'T MANY
        # RECORDS IN THE DeliveryPredictions TABLE THIS SEEMS LIKE THE MORE EFFICIENT APPROACH.  IF THE NUMBER OF RECORDS
        # INCREASES TO A POINT THAT THIS BECOMES INEFFICIENT THEN THIS WILL HAVE TO BE REFACTORED.
        params = {
            'view': 'All View'
        }
        response = requests.get(base_url + '/' + api_version + '/' + airtable_base + '/DeliveryItemPredictions', headers=self._get_headers(), params=params)
        dict_predictions = json.loads(response.text)
        # CREATE A COLLECTION TO HOLD AirtableDeliveryPrediction OBJECTS.
        airtable_predictions = AirtableDeliveryItemPredictions()
        for record in dict_predictions['records']:
            prediction = AirtableDeliveryItemPrediction(id=record['id'],
                                                        product_id=record['fields']['ProductName'][0],
                                                        agency_size=record['fields']['AgencySize'],
                                                        quantity=record['fields']['Quantity']
                                                        )
            airtable_predictions.add_prediction(prediction)

        # BUILD THE PAYLOAD AND SEND THE GET REQUEST TO GET THE RECORDS THAT NEED TO BE PROCESSED FROM THE Requests TABLE.
        # A cron_status = 0 INDICATES A RECORD THAT NEEDS TO BE PROCESSED.
        params = {
            'view': 'All submissions',
            'fields[]': ['RequestedProducts', 'AgencySize_Calc'],
            'filterByFormula': 'AND({cron_status_calc} = \'0\', {DistributorRecordId} = \'' + distributor_id + '\')'
        }
        response = requests.get(base_url + '/' + api_version + '/' + airtable_base + '/Requests', headers=self._get_headers(), params=params)
        dict_submissions = json.loads(response.text)

        if len(dict_submissions['records']) > 0:
            # DICT TO BUILD THE POST DATA
            post_payload = {
                "records": []
            }
            # WE WANT TO LIMIT THE NUMBER OF POST REQUESTS SO WE LOOP THROUGH ALL Requests TABLE RECORDS THAT NEED TO BE PROCESSED
            # TO BUILD A SINGLE PAYLOAD FOR THE POST REQUEST.
            for record in dict_submissions['records']:
                # VERIFY THAT AT LEAST ONE PRODUCT WAS REQUESTED.  IF NO PRODUCT WAS SELECTED BY END-USER
                # THEN THE RequestedProducts KEY WILL NOT BE PRESENT IN fields KEY.
                # TODO: WHAT TO DO WHEN THE END-USER HASN'T SELECTED AT LEAST ONE PRODUCT
                if 'RequestedProducts' in record['fields'].keys():
                    # LOOP THROUGH THE RequestedProducts FIELD AND GET THE PREDICTED QUANTITY FOR EACH PRODUCT
                    for product_id in record['fields']['RequestedProducts']:
                        predicted_quantity = airtable_predictions.get_prediction(product_id, record['fields']['AgencySize_Calc'])
                        # BUILD THE POST REQUEST PAYLOAD FOR THE PRODUCT
                        post_payload['records'].append(
                            {
                                "fields": {
                                    "ProductName": [product_id],
                                    "Quantity": predicted_quantity,
                                    "Delivery": [record['id']]
                                }
                            }
                        )

            # SEND THE POST REQUEST TO WRITE DATA TO DeliveredItems TABLE.
            response = requests.post(base_url + '/' + api_version + '/' + airtable_base + '/DeliveredItems', headers=self._get_headers(), json=post_payload)
            dict_delivered_items = json.loads(response.text)

            # CHECK FOR ERROR IN PREVIOUS POST REQUEST
            if 'error' not in dict_delivered_items:
                # UPDATE THE cron_status TO 1 FOR ALL SUCCESSFULLY PROCESSED Requests TABLE RECORDS
                patch_payload = {
                    "records": []
                }
                # LIST TO HOLD **UNIQUE** Requests TABLE RECORD IDS
                list_request_records = []

                # LOOP THROUGH THE RESPONSE RETURNED AFTER INSERTING DATA INTO THE DeliveredItems TABLE TO
                # RETRIEVE THE Requests TABLE RecordId (Delivery FIELD IN DeliveredItems), WHICH ARE THE RECORDS
                # THAT WILL BE UPDATED TO cron_status = 1.  WE NEED TO CREATE A LIST OF UNIQUE RecordIds.
                # SINCE EACH ITERATION IS FOR ONE PRODUCT, IF MULTIPLE PRODUCTS WERE REQUESTED THERE WILL BE THAT
                # MANY PRODUCT RECORDS IN dict_delivered_items['records'] WITH THE SAME Delivery/RecordId ID.
                for record in dict_delivered_items['records']:
                    requests_record_id = record['fields']['Delivery'][0]
                    if requests_record_id not in list_request_records:
                        list_request_records.append(requests_record_id)
                        patch_payload['records'].append({
                            'id': requests_record_id,
                            'fields': {
                                'cron_status': 1
                            }
                        })

                # SEND THE PATCH REQUEST
                response = requests.patch(base_url + '/' + api_version + '/' + airtable_base + '/Requests', headers=self._get_headers(), json=patch_payload)

    def _insert_inventory_log_on_delivery_request_completion(self, distributor_id=None):
        if self._min_config() is False:
            return

        if distributor_id is None:
            _logging = logging.getLogger(__name__)
            _logging.warning('Missing argument distributor_id.')
            return

        base_url = self.env['ir.config_parameter'].get_param('nexto.airtable.base_url')
        api_version = self.env['ir.config_parameter'].get_param('nexto.airtable.api_version')
        airtable_base = self.env['ir.config_parameter'].get_param('nexto.airtable.airtable_base')
        cron_user_id = self.env['ir.config_parameter'].get_param('nexto.airtable.cron_user_id')

        # GET RECORDS FROM THE Requests TABLE THAT HAVE BEEN COMPLETED, I.E. THE 'Delivery Workflow' STATUS IS ONE OF
        # 'Pickup Completed' OR 'Delivery Completed' AND WHERE THE cron_status == 1 INDICATING THAT THE RECORD HAS BEEN PROCESSED
        # BY THE CRON JOB THAT RUNS AFTER A RECORD IS CREATED IN THE Requests TABLE.
        params = {
            'view': 'All submissions',
            'fields[]': ['RecordId_Calc', 'LastUpdatedOn'],
            'filterByFormula': 'AND(OR({Delivery Workflow} = \'Pickup Completed\', {Delivery Workflow} = \'Delivery Completed\'), {cron_status} = \'1\', {DistributorRecordId} = \'' + distributor_id + '\')'
        }
        response = requests.get(base_url + '/' + api_version + '/' + airtable_base + '/Requests', headers=self._get_headers(), params=params)
        dict_requests_records = json.loads(response.text)

        if len(dict_requests_records['records']) > 0:
            # LOOKUP THE DeltaInventoryQuantity IN THE DeliveredItems TABLE USING RecordId_Calc (DeliveryId IN DeliveredItems TABLE)
            # BUILD THE FilterByFormula PORTION OF THE QUERY STRING FOR THE GET REQUEST BY LOOPING THROUGH THE Requests RECORDS
            # AND CONCATENATING EACH DeliveryId
            filter_by_formula = 'OR('
            for idx, record in enumerate(dict_requests_records['records']):
                if idx < len(dict_requests_records['records']) - 1:
                    filter_by_formula = filter_by_formula + '{DeliveryId} = \'' + record['id'] + '\', '
                elif idx == len(dict_requests_records['records']) - 1:
                    filter_by_formula = filter_by_formula + '{DeliveryId} = \'' + record['id'] + '\')'

            params = {
                'fields[]': ['ProductName', 'DeltaInventoryQuantity', 'DeliveryId'],
                'filterByFormula': filter_by_formula
            }
            response = requests.get(base_url + '/' + api_version + '/' + airtable_base + '/DeliveredItems', headers=self._get_headers(), params=params)
            dict_product_quantities = json.loads(response.text)

            # LOOP THROUGH dict_product_quantities TO BUILD THE POST PAYLOAD FOR CREATING RECORDS IN InventoryLog TABLE TO
            # DECREMENT THE INVENTORY.
            post_payload = {
                "records": []
            }
            for record in dict_product_quantities['records']:
                product_name = record['fields']['ProductName'][0]
                fulfilled_delivery_request = record['fields']['DeliveryId'][0]
                delta_inventory_quantity = record['fields']['DeltaInventoryQuantity']

                post_payload['records'].append({
                    'fields': {
                        'ProductName': [product_name],
                        'DeltaOnHandQuantity': delta_inventory_quantity,
                        'FulfilledDeliveryRequest': [fulfilled_delivery_request],
                        'CreatedBy': [cron_user_id]
                    }
                })
            response = requests.post(base_url + '/' + api_version + '/' + airtable_base + '/InventoryLog', headers=self._get_headers(), json=post_payload)
            dict_inventories = json.loads(response.text)

            # UPDATE THE cron_status TO 2 FOR ALL SUCCESSFULLY PROCESSED DeliveredItems TABLE RECORDS
            patch_payload = {
                "records": []
            }
            # LIST TO HOLD **UNIQUE** Requests TABLE RECORD IDS
            list_request_records = []

            # LOOP THROUGH THE RESPONSE RETURNED AFTER INSERTING DATA INTO THE InventoryLog TABLE TO
            # RETRIEVE THE Requests TABLE RecordId (FulfilledDeliveryRequest FIELD IN InventoryLog), WHICH ARE THE RECORDS
            # THAT WILL BE UPDATED TO cron_status = 2.  WE NEED TO CREATE A LIST OF UNIQUE RecordIds.
            # IF MORE THAN ONE INVENTORY RECORD WAS CREATED FOR A SINGLE Request RECORD THEN THERE WILL BE THAT
            # MANY INVENTORY RECORDS IN dict_inventories['records']['fields']['FulfilledDeliveryRequest']
            # WITH THE SAME Requests TABLE RECORD ID.
            for record in dict_inventories['records']:
                requests_record_id = record['fields']['FulfilledDeliveryRequest'][0]
                if requests_record_id not in list_request_records:
                    list_request_records.append(requests_record_id)
                    patch_payload['records'].append({
                        'id': requests_record_id,
                        'fields': {
                            'DeliveredOn': datetime.now(tz=timezone.utc).isoformat(),
                            'cron_status': 2
                        }
                    })

            # SEND THE PATCH REQUEST
            response = requests.patch(base_url + '/' + api_version + '/' + airtable_base + '/Requests', headers=self._get_headers(), json=patch_payload)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    default_base_url = fields.Char(default_model='nexto.airtable')
    default_api_version = fields.Char(default_model='nexto.airtable')
    default_airtable_base = fields.Char(default_model='nexto.airtable')
    default_api_token = fields.Char(default_model='nexto.airtable')
    default_cron_user_id = fields.Char(default_model='nexto.airtable')

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res.update(
            default_base_url=self.env['ir.config_parameter'].sudo().get_param('nexto.airtable.base_url'),
            default_api_version=self.env['ir.config_parameter'].sudo().get_param('nexto.airtable.api_version'),
            default_api_token=self.env['generic.crypto.param'].sudo().get_param('nexto.airtable.api_token'),
            default_airtable_base=self.env['ir.config_parameter'].sudo().get_param('nexto.airtable.airtable_base'),
            default_cron_user_id=self.env['ir.config_parameter'].sudo().get_param('nexto.airtable.cron_user_id'),
        )
        return res

    @api.model
    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param('nexto.airtable.base_url', self.default_base_url)
        self.env['ir.config_parameter'].sudo().set_param('nexto.airtable.api_version', self.default_api_version)
        self.env['ir.config_parameter'].sudo().set_param('nexto.airtable.airtable_base', self.default_airtable_base)
        self.env['generic.crypto.param'].sudo().set_param('nexto.airtable.api_token', self.default_api_token)
        self.env['ir.config_parameter'].sudo().set_param('nexto.airtable.cron_user_id', self.default_cron_user_id)
