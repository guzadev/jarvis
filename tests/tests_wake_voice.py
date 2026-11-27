"""Pending wake handoff with no physical audio, browser, or network access."""
import tempfile
import time
import unittest
from threading import Event
from unittest.mock import patch

from wake_word import WakeListener
from wake_transcriber import KEYWORD


class PendingWakeTests(unittest.TestCase):
    def test_observed_spanish_invocation(self):
        self.assertRegex("¿Garvis? ¿Estás ahí?", KEYWORD)
        self.assertRegex("Gervis, estás ahí.", KEYWORD)
        self.assertRegex("Hola, Jarvis.", KEYWORD)
        for phrase in ("Garvis", "La empresa Garvis está ahí.", "Jardines", "Buenos días", "Superjarvis"):
            self.assertNotRegex(phrase, KEYWORD)

    def test_close_or_minimize_never_reopens_the_interface(self):
        with tempfile.TemporaryDirectory() as folder:
            for closes in (True,False):
                with self.subTest(closes=closes):
                    opened=Event()
                    w=WakeListener(folder,opened.set)
                    w.config["enabled"]=True
                    now=[time.monotonic()]
                    with patch("wake_word.time.monotonic",side_effect=lambda:now[0]):
                        w.poll("old",False,True)
                        w._detected()
                        self.assertFalse(opened.is_set())
                        if closes:
                            now[0]+=6
                        else:
                            w.poll("old",False,False)
                        w._open_pending_interface()
                        self.assertFalse(opened.is_set())
                        self.assertFalse(w._listening_allowed())
                        w._open_pending_interface()
                        self.assertFalse(opened.is_set())
                        self.assertFalse(w.poll("desktop",False,True)["activate"])

    def test_background_service_never_opens_microphone_or_launches_ui(self):
        with tempfile.TemporaryDirectory() as folder:
            opened=Event();w=WakeListener(folder,opened.set);w.config['enabled']=True
            self.assertFalse(w._listening_allowed())
            w._detected();w._open_pending_interface()
            self.assertFalse(opened.is_set());self.assertEqual(w.pending,0)
            w.poll('visible',False,True)
            self.assertTrue(w._listening_allowed())
            w.release('visible')
            self.assertFalse(w._listening_allowed())

    def test_claim_before_expiry_suppresses_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            opened=Event()
            w=WakeListener(folder,opened.set)
            w.config["enabled"]=True
            w.poll("web",False,True)
            w._detected()
            self.assertTrue(w.poll("web",False,True)["activate"])
            w._open_pending_interface()
            self.assertFalse(opened.is_set())

