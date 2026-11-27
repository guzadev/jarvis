"""Cold voice preparation must not block the desktop or start duplicate loads."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import app_api


class VoicePreparation(unittest.TestCase):
    def setUp(self):
        self.previous=app_api.voice_preparation_status()
        self.profile=app_api.VOICE_PREPARED_PROFILE
        app_api.VOICE_PREPARED_PROFILE=None
        with app_api.VOICE_PREPARATION_STATE_LOCK:
            app_api.VOICE_PREPARATION_STATE.update(state='idle',ready=False,message='')
        self.finished=threading.Event()

    def tearDown(self):
        self.finished.wait(2)
        app_api.VOICE_PREPARED_PROFILE=self.profile
        with app_api.VOICE_PREPARATION_STATE_LOCK:app_api.VOICE_PREPARATION_STATE.update(self.previous)

    def test_cold_model_is_background_and_duplicate_requests_share_load(self):
        release=threading.Event()
        started=threading.Event()
        def prepare():
            started.set()
            release.wait(2)
            with app_api.VOICE_PREPARATION_STATE_LOCK:
                app_api.VOICE_PREPARATION_STATE.update(state='ready',ready=True,message='Lista')
            self.finished.set()
        with patch.object(app_api,'prepare_live_speech',side_effect=prepare) as worker:
            before=time.monotonic()
            first=app_api.start_voice_preparation()
            self.assertLess(time.monotonic()-before,.2)
            self.assertTrue(started.wait(1))
            second=app_api.start_voice_preparation()
            self.assertEqual(first['state'],'preparing')
            self.assertEqual(second['state'],'preparing')
            self.assertEqual(worker.call_count,1)
            release.set()
            self.assertTrue(self.finished.wait(1))
        self.assertTrue(app_api.voice_preparation_status()['ready'])

    def test_worker_failure_is_safe_retryable_and_visible(self):
        def failed():
            self.finished.set()
            raise RuntimeError('private internal diagnostic')
        with patch.object(app_api,'prepare_live_speech',side_effect=failed):
            app_api.start_voice_preparation()
            for _ in range(50):
                result=app_api.voice_preparation_status()
                if result['state']=='error':break
                time.sleep(.01)
        self.assertEqual(result['state'],'error')
        self.assertFalse(result['ready'])
        self.assertNotIn('private',str(result))
        self.assertIn('reintentarlo',result['message'])

    def test_cached_profile_does_not_bypass_revoked_approval(self):
        app_api.VOICE_PREPARED_PROFILE='fixture-profile'
        profile={'approved':False,'engine':'Qwen3-TTS-12Hz-1.7B-Base','profile_sha256':'fixture-profile'}
        health=SimpleNamespace(json=lambda:{'ready':True,'engine':profile['engine']})
        def revoked():
            self.finished.set()
            raise RuntimeError('Not approved')
        with patch('owned_voice.status',return_value=profile),patch.object(app_api.httpx,'get',return_value=health),patch.object(app_api,'prepare_live_speech',side_effect=revoked):
            app_api.start_voice_preparation()
            for _ in range(50):
                result=app_api.voice_preparation_status()
                if result['state']=='error':break
                time.sleep(.01)
        self.assertFalse(result['ready'])
        self.assertEqual(result['state'],'error')


if __name__=='__main__':unittest.main()
