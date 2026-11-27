"""Recognition work never discards a pending invocation just because it is busy."""
import queue
import threading
import time
import unittest
from types import SimpleNamespace

import numpy as np
from whisper_wake import WhisperWake, Capture


class WakeBackpressure(unittest.TestCase):
    def fixture(self):
        worker=WhisperWake.__new__(WhisperWake)
        worker.process=SimpleNamespace(poll=lambda:None)
        worker.failed=threading.Event()
        worker.ready=threading.Event();worker.ready.set()
        worker.jobs=queue.Queue(maxsize=1);worker.results=queue.Queue(maxsize=1)
        worker.started=worker.submitted=time.monotonic()
        worker.busy=True;worker.serial=1
        worker.active=Capture()
        worker.active.pending=(16000,np.ones(3200,dtype=np.float32)*.1)
        return worker,worker.active

    def test_phrase_waits_for_decoder_instead_of_being_discarded(self):
        worker,stream=self.fixture()
        self.assertFalse(worker.is_ready(stream))
        worker.decode_stream(stream)
        self.assertIsNotNone(stream.pending)
        self.assertTrue(worker.jobs.empty())
        worker.results.put_nowait((stream,False))
        self.assertTrue(worker.is_ready(stream))
        worker.decode_stream(stream)
        self.assertIsNone(stream.pending)
        serial,owner,rate,samples=worker.jobs.get_nowait()
        self.assertEqual(serial,2);self.assertIs(owner,stream)
        self.assertEqual(rate,16000);self.assertEqual(len(samples),3200)
        worker.results.put_nowait((stream,True))
        worker.decode_stream(stream)
        self.assertEqual(worker.get_result(stream),'JARVIS')

    def test_hit_is_not_delayed_by_a_later_pending_phrase(self):
        worker,stream=self.fixture()
        worker.results.put_nowait((stream,True))
        worker.decode_stream(stream)
        self.assertEqual(worker.get_result(stream),'JARVIS')
        self.assertTrue(worker.jobs.empty())


if __name__=='__main__':unittest.main()
