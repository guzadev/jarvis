"""Editable outputs belong to Documents; historical downloads stay immutable."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import app_api
import app_runtime
import mission_manager
import server


class ProjectDocuments(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.storage=self.root/'internal'
        self.documents=self.root/'Documents'
        self.config={'storage_dir':str(self.storage),'projects_dir':str(self.documents/'Jarvis')}
        self.enterContext(patch.object(app_runtime,'settings',side_effect=lambda:dict(self.config)))
        self.enterContext(patch.object(app_runtime,'documents_folder',return_value=self.documents))

    def test_general_and_named_projects_are_separate_under_documents(self):
        general=mission_manager.workspace('aurelio')
        named=mission_manager.workspace('general')
        self.assertEqual(general,self.documents/'Jarvis'/'General')
        self.assertEqual(named,self.documents/'Jarvis'/'Proyectos'/'general')
        self.assertFalse(named.is_relative_to(general))
        with self.assertRaises(ValueError):mission_manager.workspace('../escape')

    def test_new_install_defaults_to_documents(self):
        self.config.pop('projects_dir')
        self.assertEqual(mission_manager.workspace(),self.documents/'Jarvis'/'General')

    def test_legacy_install_keeps_its_files_until_location_is_selected(self):
        self.config.pop('projects_dir')
        legacy=self.storage/'projects'/'aurelio';legacy.mkdir(parents=True)
        (legacy/'existing.txt').write_text('existing')
        self.assertEqual(mission_manager.workspace(),legacy)
        self.assertEqual((legacy/'existing.txt').read_text(),'existing')

    def test_intermediate_junction_is_rejected_before_creating_project(self):
        parent=self.documents/'Jarvis'/'Proyectos'
        with patch.object(Path,'is_junction',autospec=True,side_effect=lambda path:path==parent):
            with self.assertRaises(ValueError):mission_manager.workspace('external')
        self.assertFalse((parent/'external').exists())

    def test_open_uses_editable_document_and_download_retains_original(self):
        content=b'office fixture';name='document.xlsx';identifier='fixture-mission'
        editable=mission_manager.workspace()/name;editable.write_bytes(content)
        snapshot=self.storage/'artifacts'/identifier/name;snapshot.parent.mkdir(parents=True);snapshot.write_bytes(content)
        receipt={'type':'office_receipt','path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        mission={'id':identifier,'status':'done','project':'aurelio','events':[receipt],'artifacts':[{'path':name}]}
        with patch.object(server.agent_store,'mission',return_value=mission),patch.object(server,'_catalog_executable',return_value=Path('fixture/EXCEL.exe')),patch.object(server.subprocess,'Popen') as launch:
            server.open_artifact(identifier,server.OpenArtifactIn(path=name))
            self.assertEqual(launch.call_args.args[0][1],str(editable))
            editable.write_bytes(b'edited later')
            with self.assertRaises(HTTPException):server.open_artifact(identifier,server.OpenArtifactIn(path=name))
        with patch.object(app_api,'get_mission',return_value=mission):
            response=app_api.mission_file(identifier,name)
        self.assertEqual(Path(response.path).read_bytes(),content)


if __name__=='__main__':unittest.main()
