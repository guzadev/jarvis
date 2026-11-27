from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import app_api
import integrations
from integrations import Registry
from integration_store import Store

class IntegrationRoutes(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.jobs=[]
        def transport(job):
            self.jobs.append(job)
            return {'status':'ok','http_status':200,'data':{'value':0}}
        registry=Registry(Store(Path(self.folder.name)/'state.sqlite'),transport)
        self.patcher=patch.object(integrations,'REGISTRY',registry);self.patcher.start();self.addCleanup(self.patcher.stop)
        app=FastAPI();app.include_router(app_api.router);self.client=TestClient(app);self.addCleanup(self.client.close)
        self.draft={'name':'Fixture','base_url':'https://example.org','auth':{'type':'none'},'pricing':'free','daily_limit':5,
            'operations':[{'id':'read','method':'GET','path':'/item','parameters':[],'enabled':False},
                          {'id':'write','method':'POST','path':'/item','parameters':[],'enabled':True}]}

    def test_preview_save_toggle_and_call(self):
        preview=self.client.post('/api/integrations/preview',json=self.draft)
        self.assertEqual(preview.status_code,200)
        saved=self.client.post('/api/integrations',json={'draft':preview.json()['draft']}).json()['integration']
        url='/api/integrations/'+saved['id']
        self.assertEqual(self.client.post(url+'/call',json={'operation_id':'read'}).status_code,400)
        self.assertFalse(self.jobs)
        updated=self.client.patch(url,json={'operations':[{'id':'read','enabled':True}]})
        self.assertEqual(updated.status_code,200)
        result=self.client.post(url+'/call',json={'operation_id':'read'}).json()
        self.assertEqual(result['status'],'ok');self.assertEqual(result['fields'][0]['value'],0)
        self.assertEqual(self.client.delete(url).status_code,200)
        self.assertFalse(self.client.get('/api/integrations').json()['integrations'])

    def test_write_requires_separate_concrete_approval(self):
        saved=self.client.post('/api/integrations',json={'draft':self.draft}).json()['integration']
        result=self.client.post('/api/integrations/'+saved['id']+'/call',json={'operation_id':'write'}).json()
        self.assertEqual(result['status'],'needs_approval');self.assertFalse(self.jobs)
        self.assertEqual(result['preview']['method'],'POST')
        denied=self.client.post('/api/integrations/approvals/'+result['approval_id'],json={'approve':False})
        self.assertEqual(denied.json()['status'],'cancelled');self.assertFalse(self.jobs)

    def test_invalid_configuration_never_echoes_key(self):
        result=self.client.post('/api/integrations',json={'draft':None,'api_key':'private-fixture-only'})
        self.assertNotIn('private-fixture-only',result.text)
        self.assertGreaterEqual(result.status_code,400)

if __name__=='__main__':unittest.main()
