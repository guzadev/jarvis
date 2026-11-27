import tempfile
import threading
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

import httpx
import local_models as m


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.folder=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.config=dict(ollama_url="http://127.0.0.1:11435",storage_dir=str(self.folder),
                         provider="openai",local_model="qwen3:8b",conversation_provider="auto",voice="owned")
        self.enterContext(patch.object(m.app_runtime,"settings",return_value=self.config))
        self.save=self.enterContext(patch.object(m.app_runtime,"save_settings"))
        self.warm=self.enterContext(patch.object(m.app_runtime,"warm_local_model"))
        self.enterContext(patch.object(m.agent_store,"DATABASE",self.folder/"fixture.sqlite"))
        self.disk=self.enterContext(patch.object(m.shutil,"disk_usage",return_value=SimpleNamespace(free=40*1024**3)))

    def transport(self,handler):
        original=httpx.Client
        def factory(**opts):
            self.assertFalse(opts["trust_env"])
            self.assertFalse(opts["follow_redirects"])
            return original(transport=httpx.MockTransport(handler),**opts)
        self.enterContext(patch.object(m.httpx,"Client",side_effect=factory))

    def test_catalog_and_existing_tags(self):
        models=m.catalog()
        self.assertEqual([x["download_bytes"] for x in models],[1400000000,2500000000,5200000000,9300000000])
        self.transport(lambda req:httpx.Response(200,json={"models":[{"name":"qwen3:4b","size":25,"digest":"abc"}]}) if req.url.path=="/api/tags" else self.fail("unexpected network request"))
        self.assertEqual(m.installed()["installed"],[{"name":"qwen3:4b","bytes":25,"digest":"abc"}])
        m.select("qwen3:4b")
        self.save.assert_called_once_with({"provider":"local","local_model":"qwen3:4b","conversation_provider":"openai"})
        m._provision("qwen3:4b",threading.Event())

    def test_remote_daemon_rejected(self):
        with self.assertRaises(ValueError):
            m._loopback("http://example.org:11434")

    def test_hash_mismatch_keeps_runtime_absent(self):
        client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b"damaged")))
        with client,self.assertRaisesRegex(ValueError,"huella"):
            m._install(client,self.folder,threading.Event())
        self.assertFalse((self.folder/"tools/ollama").exists())
        self.assertEqual(list((self.folder/"tools").iterdir()),[])

    def test_reject_zip_parent(self):
        archive=self.folder/"model.zip"
        with zipfile.ZipFile(archive,"w") as z:z.writestr("../escape.exe","fixture")
        with self.assertRaisesRegex(ValueError,"Ruta"):
            m._extract(archive,self.folder,threading.Event())

    def test_coalesce_cancel_and_late_success(self):
        entered=threading.Event();release=threading.Event()
        def delayed(*_):
            entered.set();release.wait(3)
        with patch.object(m,"_provision",side_effect=delayed) as provision:
            m.prepare("qwen3:4b",{})
            self.assertTrue(entered.wait(1))
            worker=m._worker
            try:
                m.prepare("qwen3:4b",{})
                with self.assertRaises(ValueError):m.prepare("qwen3:8b",{})
                self.assertEqual(m.cancel()["state"],"cancelled")
                self.save.assert_not_called()
            finally:
                release.set();worker.join(2)
            provision.assert_called_once()
            self.save.assert_not_called()
            self.assertEqual(m.state()["state"],"cancelled")

    def test_pull_success_must_be_confirmed(self):
        paths=[]
        def handler(r):
            paths.append(r.url.path)
            self.save.assert_not_called()
            if r.url.path=="/api/tags":
                return httpx.Response(200,json={"models":[]})
            return httpx.Response(200,text='{"status":"success"}\n')
        self.transport(handler)
        m._run("qwen3:8b",threading.Event())
        self.assertEqual(paths,["/api/tags","/api/pull","/api/tags"])
        self.assertEqual(m.state()["state"],"error")
        self.save.assert_not_called()

    def test_remove_active_and_unknown_denied(self):
        self.config.update(provider="local")
        with self.assertRaisesRegex(ValueError,"activo"):m.remove("qwen3:8b")
        self.transport(lambda r:httpx.Response(200,json={"models":[]}) if r.method=="GET" else self.fail("Unexpected delete"))
        with self.assertRaisesRegex(ValueError,"no figura"):m.remove("qwen3:4b")

    def test_select_during_download_activates_after_verification(self):
        entered=threading.Event();release=threading.Event()
        def verify(*_):
            entered.set();release.wait(2)
        with patch.object(m,"_provision",side_effect=verify):
            m.prepare("qwen3:4b")
            self.assertTrue(entered.wait(1))
            worker=m._worker
            try:
                m.prepare("qwen3:4b",{})
                self.save.assert_not_called()
            finally:
                release.set();worker.join(2)
        self.save.assert_called_once_with({"provider":"local","local_model":"qwen3:4b","conversation_provider":"openai"})

    def test_remove_uses_daemon_only(self):
        deleted=[]
        def handler(req):
            if req.method=="DELETE":
                deleted.append((req.url.path,req.content))
                return httpx.Response(200)
            return httpx.Response(200,json={"models":[{"name":"qwen3:4b"}]})
        self.transport(handler)
        self.assertEqual(m.remove("qwen3:4b")["status"],"ok")
        self.assertEqual(deleted,[("/api/delete",b'{"model":"qwen3:4b"}')])
        self.save.assert_not_called()

    def test_active_mission_blocks_removal_after_provider_change(self):
        self.transport(lambda r:httpx.Response(200,json={"models":[{"name":"qwen3:4b"}]}) if r.method=="GET" else self.fail("Unexpected delete"))
        with m.agent_store.connect() as db:
            db.execute("INSERT INTO missions(id,provider,model,status) VALUES ('fixture','local','qwen3:4b','awaiting_approval')")
        with self.assertRaisesRegex(ValueError,"misión"):m.remove("qwen3:4b")

    def test_space_checks_before_network_transfers(self):
        self.disk.return_value=SimpleNamespace(free=100)
        with self.assertRaisesRegex(ValueError,"espacio"):m._install(None,self.folder,threading.Event())
        self.transport(lambda r:httpx.Response(200,json={"models":[]}) if r.method=="GET" else self.fail("Unexpected download"))
        with self.assertRaisesRegex(ValueError,"espacio"):m._provision("qwen3:14b",threading.Event())
