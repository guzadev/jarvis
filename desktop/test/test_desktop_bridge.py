"""Wake activation chooses the live desktop without opening another browser."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import server


class DesktopBridge(unittest.TestCase):
    def test_live_bridge_is_loopback_and_authenticated(self):
        with tempfile.TemporaryDirectory(prefix='jarvis-bridge-test-') as temporary:
            root=Path(temporary)
            (root/'.jarvis-desktop.json').write_text(json.dumps(dict(port=19001,token='test-token',updated=time.time())),encoding='utf8')
            client=MagicMock()
            client.__enter__.return_value.post.return_value.is_success=True
            with patch.object(server,'ROOT',root),patch.object(server.httpx,'Client',return_value=client) as factory,patch('webbrowser.open') as browser:
                server._open_voice_interface()
                factory.assert_called_once_with(trust_env=False,timeout=2)
                client.__enter__.return_value.post.assert_called_once_with('http://127.0.0.1:19001/show',headers={'Authorization':'Bearer test-token'})
                browser.assert_not_called()

    def test_expired_future_or_invalid_bridge_uses_browser(self):
        cases=[dict(port=19001,token='test-token',updated=time.time()-30),dict(port=19001,token='test-token',updated=time.time()+30),dict(port='19001/elsewhere',token='test-token',updated=time.time())]
        for data in cases:
            with self.subTest(data=data),tempfile.TemporaryDirectory(prefix='jarvis-bridge-test-') as temporary:
                root=Path(temporary)
                (root/'.jarvis-desktop.json').write_text(json.dumps(data),encoding='utf8')
                with patch.object(server,'ROOT',root),patch.object(server.httpx,'Client') as client,patch('webbrowser.open') as browser:
                    server._open_voice_interface()
                    client.assert_not_called()
                    browser.assert_called_once_with('http://127.0.0.1:8788')

if __name__=='__main__':unittest.main()
