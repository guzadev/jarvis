"""Contention and cancellation with a fake producer and in-memory loopback transport."""
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx

import owned_voice
from owned_voice_service import forward_pcm


class ContentionTests(unittest.TestCase):
    def test_cancel_waiting_for_headers_or_first_pcm(self):
        for headers_sent in (False, True):
            with self.subTest(headers_sent=headers_sent):
                received=threading.Event()
                disconnected=threading.Event()
                cancelled=threading.Event()
                finished=threading.Event()
                errors=[]
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_POST(self):
                        self.rfile.read(int(self.headers["Content-Length"]))
                        if headers_sent:
                            self.send_response(200)
                            self.send_header("X-Audio-Format","pcm_s16le")
                            self.send_header("X-Audio-Sample-Rate","24000")
                            self.send_header("Content-Length","64000")
                            self.end_headers()
                        received.set()
                        self.connection.settimeout(3)
                        if self.connection.recv(1)==b"":
                            disconnected.set()
                with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
                    listener=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.02},daemon=True)
                    listener.start()
                    try:
                        with patch.object(owned_voice,"URL",f"http://127.0.0.1:{server.server_port}"), patch.object(owned_voice,"status",return_value={"approved":True,"engine":owned_voice.QWEN_ENGINE}), patch.object(owned_voice,"ensure_service",return_value="fixture"), patch.object(owned_voice.SERVICE_HTTP,"get",return_value=httpx.Response(200,json={"streaming":True})):
                            def read():
                                try:next(owned_voice.synthesize_stream("fixture",cancelled))
                                except Exception as error:errors.append(type(error))
                                finally:finished.set()
                            worker=threading.Thread(target=read,daemon=True)
                            worker.start()
                            self.assertTrue(received.wait(3))
                            cancelled.set()
                            self.assertTrue(disconnected.wait(1))
                            self.assertTrue(finished.wait(1))
                            self.assertEqual(errors,[owned_voice.VoiceStreamCancelled])
                            self.assertFalse(any(t.name=="jarvis-pcm-cancel" for t in threading.enumerate()))
                    finally:
                        cancelled.set()
                        server.shutdown()
                        listener.join(1)

    def stream(self, handler):
        self.enterContext(patch.object(owned_voice.time, "sleep"))
        self.enterContext(patch.object(owned_voice, "status", return_value={"approved":True,"engine":owned_voice.QWEN_ENGINE}))
        self.enterContext(patch.object(owned_voice, "ensure_service", return_value="test"))
        def respond(request):
            if request.url.path=="/health":
                return httpx.Response(200,json={"streaming":True})
            return handler()
        client=self.enterContext(httpx.Client(transport=httpx.MockTransport(respond)))
        self.enterContext(patch.object(owned_voice,"SERVICE_HTTP",client))
        return owned_voice.synthesize_stream("Prueba sintética")

    def test_interruption_releases_lock_on_next_attempt(self):
        codes=iter((429,429,200))
        def handler():
            return httpx.Response(next(codes),content=b"pcm",headers={"x-audio-format":"pcm_s16le","x-audio-sample-rate":"24000"})
        self.assertEqual(b"".join(self.stream(handler)),b"pcm")

    def test_persistent_busy_is_bounded(self):
        calls=[]
        def handler():
            calls.append(1)
            return httpx.Response(429)
        with self.assertRaises(owned_voice.VoiceBusyError):
            next(self.stream(handler))
        self.assertEqual(len(calls),5)

    def test_503_not_retried(self):
        calls=[]
        def handler():
            calls.append(1)
            return httpx.Response(503)
        with self.assertRaises(RuntimeError):
            next(self.stream(handler))
        self.assertEqual(len(calls),1)

    def test_disconnect_while_queueing_stops_before_next_gpu_step(self):
        steps=[]
        stop=threading.Event()
        def model():
            for frame in (1,2,3):
                steps.append(frame)
                yield bytes([frame])
        forward_pcm(model(),stop,lambda _:stop.set())
        self.assertEqual(steps,[1])

