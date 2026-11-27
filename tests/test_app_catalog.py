"""Application detection includes per-user installs without accepting arbitrary paths."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server
from fastapi import HTTPException


class AppCatalog(unittest.TestCase):
    def test_vscode_user_install_is_found_and_unknown_names_are_not_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            local=Path(temporary).resolve()/'Local'
            executable=local/'Programs/Microsoft VS Code/Code.exe'
            executable.parent.mkdir(parents=True);executable.write_bytes(b'fixture')
            with patch.dict(server.os.environ,{'LOCALAPPDATA':str(local),'ProgramW6432':'','ProgramFiles':'','ProgramFiles(x86)':''}):
                self.assertEqual(server._catalog_executable('vscode'),executable)
                self.assertEqual(server._catalog_executable('vsc'),executable)
                self.assertIsNone(server._catalog_executable(str(executable)))
                self.assertIsNone(server._catalog_executable('unknown-program'))

    def test_windows_apps_keep_their_system_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();executable=root/'System32/calc.exe'
            executable.parent.mkdir();executable.write_bytes(b'fixture')
            with patch.dict(server.os.environ,{'SystemRoot':str(root)}):
                self.assertEqual(server._catalog_executable('calculadora'),executable)

    def test_web_project_opens_the_html_in_a_confirmed_visible_browser_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary).resolve();html=folder/'Calculadora demo.html';html.write_text('<title>Calculadora demo</title><html>demo</html>')
            with patch.object(server.mission_manager,'workspace',return_value=folder),patch.object(server,'_catalog_executable',return_value=Path('chrome.exe')),patch.object(server,'_visible_windows',side_effect=[{1:'Old Chrome'},{1:'Old Chrome',2:'Calculadora demo - Google Chrome'}]),patch.object(server.subprocess,'Popen') as launch:
                result=server.open_web_project('aurelio',server.OpenArtifactIn(path=html.name))
            self.assertTrue(result['ok'])
            self.assertEqual(launch.call_args.args[0],['chrome.exe','--new-window',html.as_uri()])
            self.assertEqual(launch.call_args.kwargs['startupinfo'].wShowWindow,1)
            self.assertIn('Google Chrome',result['window'])

    def test_web_project_rejects_unsafe_paths_and_does_not_claim_unseen_windows(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary).resolve();(folder/'demo.html').write_text('<html>demo</html>')
            with patch.object(server.mission_manager,'workspace',return_value=folder),patch.object(server.subprocess,'Popen') as launch:
                for name in ('../escape.html','demo.exe','missing.html'):
                    with self.assertRaises(HTTPException):server.open_web_project('aurelio',server.OpenArtifactIn(path=name))
                launch.assert_not_called()
                with patch.object(server,'_catalog_executable',return_value=Path('chrome.exe')),patch.object(server,'_visible_windows',return_value={1:'Old Chrome'}),patch.object(server.time,'monotonic',side_effect=[0,1,7]),patch.object(server.time,'sleep'):
                    result=server.open_web_project('aurelio',server.OpenArtifactIn(path='demo.html'))
                self.assertFalse(result['ok'])
                with patch.object(server,'_catalog_executable',return_value=Path('chrome.exe')),patch.object(server,'_visible_windows',side_effect=[{1:'Old Chrome'},{1:'Old Chrome',2:'demo.html - Microsoft Edge'}]),patch.object(server.time,'monotonic',side_effect=[0,1,7]),patch.object(server.time,'sleep'):
                    self.assertFalse(server.open_web_project('aurelio',server.OpenArtifactIn(path='demo.html'))['ok'])


if __name__=='__main__':unittest.main()
