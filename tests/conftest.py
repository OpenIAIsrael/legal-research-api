import os
import sys
from pathlib import Path
os.environ['LEGAL_INDEX_BACKGROUND']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest

@pytest.fixture(autouse=True)
def isolated_sources(monkeypatch,tmp_path):
    import legislation,stj_index,official_http,time
    async def unavailable(*args,**kwargs):raise official_http.SourceError('Fonte indisponível no teste isolado')
    monkeypatch.setattr(legislation,'fetch',unavailable)
    monkeypatch.setattr(stj_index,'fetch',unavailable)
    monkeypatch.setattr(stj_index,'DB',tmp_path/'index.sqlite3')
    monkeypatch.setattr(stj_index,'LAST_REFRESH',time.monotonic())
    monkeypatch.setattr(stj_index,'STATE',{'status':'ready','resources':[],'warnings':[],'complete':False})
