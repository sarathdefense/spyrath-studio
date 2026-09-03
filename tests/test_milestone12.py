from pathlib import Path
import pytest
from spyrath.studio.accounts import AccountStore
from spyrath.studio.security import AccessController, SecurityConfig
from spyrath.storage import LocalArtifactStorage
from spyrath.studio import create_app
from spyrath.studio import ProjectRepository, StudioService

def make_service(tmp_path):
    return StudioService(repository=ProjectRepository(tmp_path/"projects"), orchestrator_factory=lambda spec, root: None)

def test_account_auth_and_project_ownership(tmp_path):
    a=AccountStore(tmp_path/'studio.db'); a.ensure_user('alice','Alice','secret-a'); a.ensure_user('bob','Bob','secret-b')
    assert a.authenticate('secret-a').user_id=='alice'; assert a.authenticate('bad') is None
    a.claim_project('book','alice'); assert a.owns('book','alice'); assert not a.owns('book','bob')

def test_local_storage_is_atomic_and_path_safe(tmp_path):
    src=tmp_path/'x.bin'; src.write_bytes(b'ok'); store=LocalArtifactStorage(tmp_path/'objects')
    out=store.put(src,'alice/book/x.bin'); assert out.read_bytes()==b'ok'
    with pytest.raises(ValueError): store.resolve('../escape')

def test_authenticated_api_isolates_projects(tmp_path):
    pytest.importorskip('fastapi'); from fastapi.testclient import TestClient
    service=make_service(tmp_path); accounts=AccountStore(tmp_path/'meta.db'); accounts.ensure_user('alice','Alice','a'); accounts.ensure_user('bob','Bob','b')
    access=AccessController(accounts,SecurityConfig(enabled=True)); client=TestClient(create_app(service,access=access))
    payload={'project_id':'book','title':'Book','presenter_image':'p.png','voice_reference':'v.wav','chapters':[{'chapter_id':'c','texts':['hello']}]}
    assert client.post('/api/projects',json=payload).status_code==401
    assert client.post('/api/projects',json=payload,headers={'X-Spyrath-Key':'a'}).status_code==201
    assert [p['project_id'] for p in client.get('/api/projects',headers={'X-Spyrath-Key':'a'}).json()['projects']]==['book']
    assert client.get('/api/projects',headers={'X-Spyrath-Key':'b'}).json()['projects']==[]
    assert client.get('/api/projects/book',headers={'X-Spyrath-Key':'b'}).status_code==404
