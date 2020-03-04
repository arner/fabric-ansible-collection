#!/usr/bin/python
#
# SPDX-License-Identifier: Apache-2.0
#

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible.errors import AnsibleActionFail
from ansible.module_utils.urls import open_url

import base64
import json
import time
import urllib.parse

class BlockchainPlatform:

    def __init__(self, api_endpoint, api_timeout):
        self.api_endpoint = api_endpoint
        self.api_timeout = api_timeout
        self.authorization = None

    def login(self, api_authtype, api_key, api_secret):
        if api_authtype == 'ibmcloud':
            self._login_ibmcloud(api_key)
        elif api_authtype == 'basic':
            self._login_basic(api_key, api_secret)
        else:
            raise AnsibleActionFail(f'invalid authentication type "{api_authtype}" specified, valid values are "ibmcloud" and "basic"')
        try:
            self.get_health()
        except Exception as e:
            raise AnsibleActionFail(f'Failed to access IBM Blockchain Platform console: {e}')

    def _login_ibmcloud(self, api_key):
        try:
            data = urllib.parse.urlencode({
                'apikey': api_key,
                'grant_type': 'urn:ibm:params:oauth:grant-type:apikey'
            })
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            auth_response = open_url(url='https://iam.cloud.ibm.com/identity/token', method='POST', headers=headers, data=data, timeout=self.api_timeout)
            auth = json.load(auth_response)
            access_token = auth['access_token']
            self.authorization = f'Bearer {access_token}'
        except Exception as e:
            raise AnsibleActionFail(f'Failed to log in to IBM Cloud: {e}')

    def _login_basic(self, api_key, api_secret):
        credentials = f'{api_key}:{api_secret}'
        self.authorization = f'Basic {base64.b64encode(credentials.encode("utf8")).decode("utf8")}'

    def _ensure_loggedin(self):
        if self.authorization is None:
            raise AnsibleActionFail(f'Not logged in')

    def get_health(self):
        self._ensure_loggedin()
        url = f'{self.api_endpoint}/ak/api/v2/health'
        headers = {
            'Accepts': 'application/json',
            'Authorization': self.authorization
        }
        response = open_url(url, None, headers, 'GET', validate_certs=False, timeout=self.api_timeout)
        return json.load(response)

    def get_all_components(self, deployment_attrs='omitted'):
        self._ensure_loggedin()
        url = f'{self.api_endpoint}/ak/api/v2/components'
        headers = {
            'Accepts': 'application/json',
            'Authorization': self.authorization
        }
        response = open_url(url, None, headers, 'GET', validate_certs=False, timeout=self.api_timeout)
        parsed_response = json.load(response)
        return parsed_response.get('components', list())

    def get_component_by_id(self, id, deployment_attrs='omitted'):
        self._ensure_loggedin()
        url = f'{self.api_endpoint}/ak/api/v2/components/{id}?deployment_attrs=included'
        headers = {
            'Accepts': 'application/json',
            'Authorization': self.authorization
        }
        response = open_url(url, None, headers, 'GET', validate_certs=False, timeout=self.api_timeout)
        return json.load(response)

    def get_component_by_display_name(self, display_name, deployment_attrs='omitted'):
        components = self.get_all_components()
        ca = next((component for component in components if component.get('display_name', None) == display_name), None)
        if ca is not None:
            return self.get_component_by_id(ca['id'], deployment_attrs)

    def create_ca(self, data):
        self._ensure_loggedin()
        url = f'{self.api_endpoint}/ak/api/v2/kubernetes/components/fabric-ca'
        headers = {
            'Accepts': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': self.authorization
        }
        data = json.dumps(data)
        try:
            response = open_url(url, data, headers, 'POST', validate_certs=False, timeout=self.api_timeout)
            return json.load(response)
        except urllib.error.HTTPError as e:
            print(e)
            print(json.load(e))
            raise e

    def update_ca(self, id, data):
        self._ensure_loggedin()
        url = f'{self.api_endpoint}/ak/api/v1/kubernetes/components/fabric-ca/{id}'
        headers = {
            'Accepts': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': self.authorization
        }
        data = json.dumps(data)
        response = open_url(url, data, headers, 'PUT', validate_certs=False, timeout=self.api_timeout)
        return json.load(response)

    def delete_ca(self, id):
        self._ensure_loggedin()
        url = f'{self.api_endpoint}/ak/api/v2/kubernetes/components/{id}'
        headers = {
            'Authorization': self.authorization
        }
        open_url(url, None, headers, 'DELETE', validate_certs=False, timeout=self.api_timeout)

    def extract_ca_info(self, ca):
        return {
            'name': ca['display_name'],
            'api_url': ca['api_url'],
            'operations_url': ca['operations_url'],
            'ca_url': ca['api_url'],
            'type': 'fabric-ca',
            'ca_name': ca['ca_name'],
            'tlsca_name': ca['tlsca_name'],
            'pem': ca['tls_cert'],
            'tls_cert': ca['tls_cert'],
            'location': ca['location']
        }

    def wait_for_ca(self, ca, timeout):
        started = False
        for x in range(timeout):
            try:
                response = open_url(f'{ca["api_url"]}/cainfo', None, None, method='GET', validate_certs=False)
                if response.code == 200:
                    cainfo = json.load(response)
                    if cainfo['result']['Version'] is not None:
                        started = True
                        break
            except:
                pass
            time.sleep(1)
        if not started:
            raise AnsibleActionFail(f'Certificate authority failed to start within {timeout} seconds')
