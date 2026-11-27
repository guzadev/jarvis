"""Data route validation without provider requests or persistent credentials."""
import json
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import app_api


class DataAPI(unittest.TestCase):
    def setUp(self):
        app=FastAPI()
        app.include_router(app_api.router)
        self.client=TestClient(app)
        self.addCleanup(self.client.close)

    def test_provider_metadata_never_contains_keys(self):
        states={name:{'configured':False} for name in app_api.DATA_PROVIDERS}
        with patch.object(app_api.data_credentials,'status',return_value=states):
            result=self.client.get('/api/data/providers').json()
        self.assertEqual(set(result['providers']),set(states))
        self.assertFalse(result['providers']['nasa']['required'])
        for value in result['providers'].values():
            self.assertEqual(set(value),{'label','required','configured','help_url'})

    def test_rejected_key_never_echoes_input(self):
        secret='synthetic-private-key-for-test'
        with patch.object(app_api.data_credentials,'save_key',side_effect=ValueError(secret)):
            response=self.client.post('/api/data/providers/tomtom',json={'api_key':secret})
        self.assertEqual(response.status_code,400)
        self.assertNotIn(secret,response.text)
        response=self.client.post('/api/data/providers/tomtom',json={'api_key':secret*300})
        self.assertEqual(response.status_code,400)
        self.assertNotIn(secret,response.text)

    def test_save_does_not_return_key_and_invalidates_cache(self):
        receipt={'provider':'tomtom','configured':True}
        with patch.object(app_api.data_credentials,'save_key',return_value=receipt),patch.object(app_api.DATA,'clear_cache') as clear:
            response=self.client.post('/api/data/providers/tomtom',json={'api_key':'synthetic-private-key-for-test'})
        self.assertEqual(response.json(),receipt)
        clear.assert_called_once()

    def test_execution_dispatch_and_unknown_tool(self):
        with patch.object(app_api.DATA,'execute',return_value={'status':'ok','rows':[[1,2]]}) as execute:
            result=self.client.post('/api/data/execute',json={'name':'get_dollar','arguments':{'kind':'blue'}})
        execute.assert_called_once_with('get_dollar',{'kind':'blue'})
        self.assertEqual(result.json()['rows'],[[1,2]])
        result=self.client.post('/api/data/execute',json={'name':'unknown','arguments':{}})
        self.assertEqual(result.json()['status'],'error')

    def test_astronomy_video_receives_only_a_date_and_returns_bounded_media(self):
        with patch.object(app_api.DATA,'astronomy_video',return_value=(b'fixture-video','video/mp4')) as fetch:
            result=self.client.get('/api/data/astronomy/video?date=2026-11-25')
        fetch.assert_called_once_with('2026-11-25')
        self.assertEqual(result.content,b'fixture-video')
        self.assertEqual(result.headers['Content-Type'],'video/mp4')
        self.assertEqual(self.client.get('/api/data/astronomy/video?date=https://attacker.example').status_code,422)
        self.assertEqual(self.client.get('/api/data/astronomy/video?url=https://attacker.example').status_code,422)


if __name__=='__main__':unittest.main()
