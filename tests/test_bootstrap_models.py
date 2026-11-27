"""Offline tests for immutable voice/wake assets; no provider connection or model load."""
import hashlib
import io
import os
import tempfile
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bootstrap_models as b


class Reply(io.BytesIO):
    def __init__(self, data, status=200, start=None):
        super().__init__(data)
        self.status=status
        self.headers={} if start is None else {"Content-Range":f"bytes {start}-{start+len(data)-1}/{start+len(data)}"}


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.data=b"tiny model fixture"
        self.item=dict(path="models/whisper-small/model.bin",bytes=len(self.data),sha256=hashlib.sha256(self.data).hexdigest(),
                       url="https://huggingface.co/pinned/fixture",label="Prueba")
        self.target=self.root/self.item["path"]
        self.target.parent.mkdir(parents=True)
        self.partial=self.target.with_suffix(".bin.partial")
        self.opener=Mock()
        self.enterContext(patch.object(b,"weights",return_value=[self.item]))
        self.enterContext(patch.object(b.shutil,"disk_usage",return_value=SimpleNamespace(free=30*1024**3)))

    def prepare(self):
        b.prepare(self.root,report=lambda _:None,opener=self.opener)

    def test_range_resume_keeps_prefix(self):
        self.partial.write_bytes(self.data[:5])
        self.opener.open.return_value=Reply(self.data[5:],206,5)
        self.prepare()
        request=self.opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Range"),"bytes=5-")
        self.assertEqual(self.target.read_bytes(),self.data)
        self.assertFalse(self.partial.exists())

    def test_server_ignoring_range_replaces_prefix(self):
        self.partial.write_bytes(b"wrong")
        self.opener.open.return_value=Reply(self.data)
        self.prepare()
        self.assertEqual(self.target.read_bytes(),self.data)

    def test_wrong_content_range_rejected_before_append(self):
        self.partial.write_bytes(self.data[:5])
        self.opener.open.return_value=Reply(self.data[5:],206,3)
        with self.assertRaisesRegex(ValueError,"reanudación"):self.prepare()
        self.assertEqual(self.partial.read_bytes(),self.data[:5])
        self.assertFalse(self.target.exists())

    def test_bad_sha_preserves_old_file_and_profile(self):
        self.target.write_bytes(b"old")
        profile=self.root/"models/jarvis-owned/voice.pth"
        profile.parent.mkdir(parents=True);profile.write_bytes(b"personal profile fixture")
        self.opener.open.return_value=Reply(b"x"*len(self.data))
        with self.assertRaisesRegex(ValueError,"no coincide"):self.prepare()
        self.assertEqual(self.target.read_bytes(),b"old")
        self.assertEqual(profile.read_bytes(),b"personal profile fixture")
        self.assertFalse((self.root/".publisher-models-ready.json").exists())

    def test_verified_stamp_fast_path_does_not_fetch_or_rehash(self):
        self.opener.open.return_value=Reply(self.data)
        self.prepare()
        self.opener.reset_mock()
        with patch.object(b,"checksum",side_effect=AssertionError("unexpected large file hash")):self.prepare()
        self.opener.open.assert_not_called()

    def test_redirect_must_remain_at_publisher(self):
        req=urllib.request.Request(self.item["url"])
        redirect=b.PublisherRedirects()
        for url in ("https://huggingface.co.example.org/model","http://hf.co/model","https://hf.co:444/model","https://user@hf.co/model"):
            with self.subTest(url=url),self.assertRaises(ValueError):
                redirect.redirect_request(req,None,302,"",{},url)
        allowed=redirect.redirect_request(req,None,302,"",{},"https://cas-bridge.xethub.hf.co/x")
        self.assertEqual(allowed.full_url,"https://cas-bridge.xethub.hf.co/x")

    def test_same_size_changed_file_rechecked_and_repaired(self):
        self.opener.open.return_value=Reply(self.data)
        self.prepare()
        old=self.target.stat().st_mtime_ns
        self.target.write_bytes(b"x"*len(self.data))
        os.utime(self.target,ns=(old+2_000_000_000,old+2_000_000_000))
        self.opener.open.return_value=Reply(self.data)
        with patch.object(b,"checksum",wraps=b.checksum) as checked:self.prepare()
        self.assertEqual([c.args[0] for c in checked.call_args_list],[self.target,self.partial])
        self.assertEqual(self.target.read_bytes(),self.data)

    def test_free_space_counts_only_remaining_partial_bytes(self):
        self.partial.write_bytes(self.data[:-2])
        self.opener.open.return_value=Reply(self.data[-2:],206,len(self.data)-2)
        with patch.object(b.shutil,"disk_usage",return_value=SimpleNamespace(free=1024**3+2)):
            self.prepare()
        self.assertEqual(self.target.read_bytes(),self.data)

    def test_free_space_for_replacement_keeps_original_file(self):
        self.target.write_bytes(b"old")
        with patch.object(b.shutil,"disk_usage",return_value=SimpleNamespace(free=1024**3+2)),self.assertRaisesRegex(ValueError,"espacio"):
            self.prepare()
        self.opener.open.assert_not_called()
        self.assertEqual(self.target.read_bytes(),b"old")
