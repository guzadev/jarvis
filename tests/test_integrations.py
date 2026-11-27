import json
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from integrations import Registry
from integration_store import Store
import integration_http


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.jobs=[]
        def transport(job):
            self.jobs.append(job)
            return {"status":"ok","http_status":200,"data":{"value":0}}
        self.r=Registry(Store(Path(self.temp.name)/"registry.sqlite"), transport)
        self.raw={"name":"Test","base_url":"https://example.org/v1","pricing":"free","daily_limit":1,
                  "auth":{"type":"api_key","in":"query","name":"api_key"},
                  "operations":[{"id":"read","method":"GET","path":"/item/{id}","parameters":[{"name":"id","in":"path","type":"string"}]},
                                {"id":"write","method":"POST","path":"/item","body_schema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]},"body_required":True}]}
        self.secret="qa-fixture-token"
        self.id=self.r.save(self.raw,self.secret)["integration"]["id"]

    def test_auth_usage_and_limit(self):
        reply=self.r.call(self.id,"read",{"path":{"id":"A"}})
        self.assertEqual(reply["status"],"ok")
        self.assertEqual(self.jobs[0]["key"],self.secret)
        self.assertNotIn(self.secret,json.dumps(self.r.list()))
        with self.assertRaises(ValueError):
            self.r.call(self.id,"read",{"path":{"id":"B"}})
        self.assertEqual(len(self.jobs),1)

    def test_approval_race(self):
        preview=self.r.call(self.id,"write",{"body":{"name":"A"}})
        self.assertNotIn(self.secret,json.dumps(preview))
        def attempt(_):
            try:
                return self.r.decide(preview["approval_id"],True)["status"]
            except ValueError:
                return "unavailable"
        with ThreadPoolExecutor(2) as pool:
            self.assertCountEqual(pool.map(attempt,range(2)),["ok","unavailable"])
        self.assertEqual(len(self.jobs),1)

    def test_revision_and_expiry(self):
        for mode in ("revision","expire","reject"):
            token=self.r.call(self.id,"write",{"body":{"name":"B"}})["approval_id"]
            if mode=="revision":
                self.r.update(self.id,{"api_key":"new-fixture"})
            elif mode=="expire":
                with self.r.store.transaction() as db:
                    db.execute("UPDATE approvals SET expires=0 WHERE token=?",(token,))
            else:
                self.assertEqual(self.r.decide(token,False)["status"],"cancelled")
            with self.assertRaises(ValueError):
                self.r.decide(token,True)
        self.assertEqual(self.jobs,[])

    def test_path_and_body_fail_before_network(self):
        for args in ({"path":{"id":".."}},{"path":{"id":"//secret"}},{"headers":{"Host":"override"}},{"query":{"api_key":"other"}}):
            with self.assertRaises(ValueError):
                self.r.call(self.id,"read",args)
        with self.assertRaises(ValueError):
            self.r.call(self.id,"write",{"body":{}})
        self.assertEqual(self.jobs,[])

    def test_openapi_omit_and_public(self):
        doc={"openapi":"3.1.0","info":{"title":"demo"},"servers":[{"url":"https://example.org/v1"}],
             "security":[{"token":[]}],"components":{"securitySchemes":{"token":{"type":"http","scheme":"bearer"}}},
             "paths":{"/secure":{"get":{"operationId":"secure"}},"/public":{"get":{"security":[],"operationId":"public"}},
                      "/other":{"get":{"servers":[{"url":"https://elsewhere.org"}]}},"/multi":{"get":{"security":[{"token":[],"other":[]}]}},
                      "/ref":{"get":{"parameters":[{"$ref":"https://example.org/some.json"}]}}}}
        draft=self.r.preview({"mode":"openapi","document":doc})
        self.assertEqual(len(draft["warnings"]),3)
        integration=self.r.save(draft["draft"],self.secret)["integration"]
        token=self.r.call(integration["id"],"public",{})["approval_id"]
        self.r.decide(token,True)
        self.assertNotIn("key",self.jobs[-1])
        self.assertEqual(self.r.list("demo")["integrations"][0]["auth"]["type"],"bearer")

    def test_manual_blocked_destinations(self):
        for url in ("http://example.org","https://127.0.0.1","https://u:p@example.org","https://example.org:8443","https://example.org/b/../a","https://example.org/?token=bad"):
            with self.assertRaises(ValueError):
                self.r.preview({**self.raw,"base_url":url})

    def test_worker_pinned_tls_and_no_redirect(self):
        fixture="qa-secret+encoded"
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,"",("93.184.216.34",443))]
        transport=MagicMock()
        response=transport.getresponse.return_value
        response.headers={}
        response.status=200
        response.length=None
        response.read.return_value=json.dumps({"token":fixture,"encoded":"qa-secret%2Bencoded"}).encode()
        job={"method":"GET","url":"https://example.org/one","auth":{"type":"api_key","in":"query","name":"key"},"key":fixture}
        with patch("public_reader.socket.getaddrinfo", return_value=addresses) as lookup, patch("integration_http.socket.socket") as sockets, patch("integration_http.ssl.create_default_context") as tls, patch("integration_http.http.client.HTTPConnection",return_value=transport):
            result=integration_http.perform(job)
            lookup.assert_called_once()
            sockets.return_value.connect.assert_called_once_with(("93.184.216.34",443))
            tls.return_value.wrap_socket.assert_called_once_with(sockets.return_value,server_hostname="example.org")
            self.assertEqual(result["data"],{"token":"[privado]","encoded":"[privado]"})
            response.status=302
            response.read.reset_mock()
            self.assertEqual(integration_http.perform(job)["status"],"error")
            response.read.assert_not_called()
        self.assertEqual(transport.request.call_count,2)

    def test_worker_rejects_mixed_dns_before_socket(self):
        rows=[(socket.AF_INET,socket.SOCK_STREAM,6,"",(v,443)) for v in ("93.184.216.34","127.0.0.1")]
        with patch("public_reader.socket.getaddrinfo",return_value=rows), patch("integration_http.socket.socket") as socket_creator:
            with self.assertRaises(ValueError):
                integration_http.perform({"url":"https://example.org/one","method":"GET"})
            socket_creator.assert_not_called()


if __name__=="__main__":
    unittest.main()

