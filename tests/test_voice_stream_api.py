"""Errors identify the failed stage; cancellation releases the pre-read stream."""
import asyncio
import unittest
import threading
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
import httpx
import app_api
import owned_voice


class SpeechStreamAPI(unittest.TestCase):
    def call(self,iterator):
        async def connected():return False
        with patch('app_runtime.voice_mode',return_value='owned'),patch('owned_voice.status',return_value={'approved':True}),patch('owned_voice.synthesize_stream',return_value=iterator):
            return asyncio.run(app_api.stream_speech(app_api.SpeakIn(text='Frase de prueba.'),SimpleNamespace(is_disconnected=connected)))

    def test_busy_and_network_failures_have_distinct_safe_codes(self):
        for error,status,code in ((owned_voice.VoiceBusyError('private'),429,'voice_busy'),
                                  (httpx.ReadTimeout('private'),503,'voice_timeout'),
                                  (httpx.ConnectError('private'),503,'voice_connection'),
                                  (RuntimeError('private'),503,'voice_generation')):
            def broken():
                raise error
                yield
            with self.subTest(code=code),self.assertRaises(HTTPException) as caught:
                self.call(broken())
            self.assertEqual(caught.exception.status_code,status)
            self.assertEqual(caught.exception.headers['X-Jarvis-Voice-Error'],code)
            self.assertNotIn('private',caught.exception.detail)

    def test_empty_stream_is_not_reported_as_a_successful_audio_response(self):
        with self.assertRaises(HTTPException) as caught:self.call(iter(()))
        self.assertEqual(caught.exception.status_code,503)

    def test_disconnect_before_body_iteration_closes_preloaded_upstream(self):
        closed=[]
        def audio():
            try:
                yield b'\x00\x00'
                yield b'\x00\x00'
            finally:closed.append(True)
        response=self.call(audio())
        async def receive():return {'type':'http.disconnect'}
        async def send(message):raise OSError('downstream disconnected')
        with self.assertRaises(Exception):
            asyncio.run(response({'type':'http','asgi':{'spec_version':'2.4'}},receive,send))
        self.assertEqual(closed,[True])

    def test_disconnect_while_waiting_for_first_pcm_cancels_upstream(self):
        closed=threading.Event()
        async def disconnected():return True
        def delayed(_text,cancel_event):
            try:
                self.assertTrue(cancel_event.wait(1))
                yield b'\x00\x00'
            finally:closed.set()
        async def exercise():
            with patch('app_runtime.voice_mode',return_value='owned'),patch('owned_voice.status',return_value={'approved':True}),patch('owned_voice.synthesize_stream',side_effect=delayed):
                with self.assertRaises(HTTPException) as caught:
                    await app_api.stream_speech(app_api.SpeakIn(text='Frase de prueba.'),SimpleNamespace(is_disconnected=disconnected))
                self.assertEqual(caught.exception.status_code,499)
                for _ in range(50):
                    if closed.is_set():break
                    await asyncio.sleep(.01)
                self.assertTrue(closed.is_set())
        asyncio.run(exercise())


if __name__=='__main__':unittest.main()
