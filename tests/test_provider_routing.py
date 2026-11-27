"""Conversation and delegated jobs can use different providers with one voice."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import httpx
import app_api
import app_runtime
import server


class ProviderRouting(unittest.TestCase):
    def setUp(self):
        temporary=self.enterContext(tempfile.TemporaryDirectory())
        self.config=Path(temporary)/'settings.json'
        self.enterContext(patch.object(app_runtime,'CONFIG_PATH',self.config))

    def test_claude_tasks_keep_openai_realtime_and_owned_voice(self):
        app_runtime.save_settings({'provider':'claude','conversation_provider':'openai','voice':'owned'})
        self.assertEqual(app_runtime.conversation_provider(),'openai')
        self.assertEqual(app_runtime.voice_mode(),'owned')
        response=httpx.Response(200,json={'value':'ephemeral-fixture'})
        with patch('owned_voice.status',return_value={'approved':True}),patch.dict(server.os.environ,{'OPENAI_API_KEY':'fixture-not-a-real-key'}),patch.object(server.agent_store,'notes',return_value=[]),patch.object(server.httpx,'post',return_value=response) as create:
            session=server.create_session()
        self.assertTrue(session['local_voice'])
        request=create.call_args.kwargs['json']['session']
        self.assertEqual(request['output_modalities'],['text'])
        self.assertNotIn('output',request['audio'])
        self.assertIn('input',request['audio'])
        self.assertGreaterEqual(request['max_output_tokens'],1024)
        self.assertIn('No escribas el código',request['instructions'])
        with patch.object(app_api,'claude_command',return_value='fixture-claude'),patch.object(app_api.mission_manager,'create',return_value={'id':'fixture-mission'}) as mission:
            app_api.create_mission(app_api.MissionIn(title='Prueba',prompt='Creá un archivo.'))
        self.assertEqual(mission.call_args.args[2],'claude')

    def test_legacy_non_openai_setup_stays_local_until_explicit_selection(self):
        app_runtime.save_settings({'provider':'claude','voice':'owned'})
        self.assertEqual(app_runtime.conversation_provider(),'local')
        with patch.object(server.httpx,'post') as create,self.assertRaises(HTTPException) as caught:
            server.create_session()
        self.assertEqual(caught.exception.status_code,409)
        create.assert_not_called()

    def test_settings_save_preserves_explicit_conversation_when_omitted(self):
        app_runtime.save_settings({'provider':'openai','conversation_provider':'openai','voice':'owned'})
        with patch.object(app_api,'agent_status',return_value={'ready':True}):
            app_api.update_settings(app_api.SettingsIn(provider='claude'))
        saved=json.loads(self.config.read_text())
        self.assertEqual(saved['conversation_provider'],'openai')
        self.assertEqual(saved['provider'],'claude')
        self.assertEqual(saved['voice'],'owned')

    def test_invalid_conversation_provider_does_not_write_configuration(self):
        with self.assertRaises(ValueError):app_runtime.save_settings({'provider':'claude','conversation_provider':'invalid'})
        self.assertFalse(self.config.exists())

    def test_quota_category_survives_long_upstream_error_without_leaking_raw_details(self):
        response=httpx.Response(429,json={'error':{'message':'private-value '*100,'type':'insufficient_quota','code':'credit_balance_exhausted'}})
        failure=server._realtime_failure(response)
        body=json.loads(failure.body)
        self.assertEqual(body['error']['code'],'credit_balance_exhausted')
        self.assertEqual(body['error']['type'],'insufficient_quota')
        self.assertNotIn('private-value',failure.body.decode())

    def test_malformed_upstream_error_stays_safe_and_preserves_retry_after(self):
        response=httpx.Response(429,text='not JSON: private-value',headers={'Retry-After':'90'})
        failure=server._realtime_failure(response)
        self.assertEqual(failure.headers['Retry-After'],'90')
        self.assertEqual(json.loads(failure.body)['error']['code'],'openai_connection')
        self.assertNotIn('private-value',failure.body.decode())


if __name__=='__main__':unittest.main()
