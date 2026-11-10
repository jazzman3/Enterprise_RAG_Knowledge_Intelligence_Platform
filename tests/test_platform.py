import os
import pytest
from fastapi.testclient import TestClient
from app.core import Store, chunk_text, embed_local, answer_extractive
from app.api import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'rag.db'))
    monkeypatch.setenv('EMBEDDING_PROVIDER','local')
    monkeypatch.setenv('ANSWER_PROVIDER','extractive')
    monkeypatch.setenv('RAG_API_KEYS','adminsecret|acme|alice|admin|engineering,finance;readerkey|acme|bob|reader|engineering;financekey|acme|june|reader|finance;globexkey|globex|eve|admin|engineering')
    with TestClient(app) as c:yield c

def h(k):return {'X-API-Key':k}

def add(c,key='adminsecret',title='Operations',content='Disaster recovery target RTO is four hours. Recovery point objective is 60 minutes.',**kwargs):
    return c.post('/v1/documents',headers=h(key),json={'title':title,'content':content,**kwargs})

def test_health(client):assert client.get('/healthz').json()=={'status':'ok'}
def test_auth_required(client):assert client.post('/v1/ask',json={'query':'hello'}).status_code==401
def test_bad_key(client):assert client.get('/v1/documents',headers=h('invalid')).status_code==401
def test_reader_cannot_ingest(client):assert add(client,key='readerkey').status_code==403
def test_ingest_search_citation(client):
    r=add(client);assert r.status_code==201
    out=client.post('/v1/ask',headers=h('readerkey'),json={'query':'disaster recovery RTO'}).json()
    assert len(out['sources'])>=1
    assert out['sources'][0]['document_id']==r.json()['document_id']
    assert '[1]' in out['answer']
def test_group_isolation(client):
    add(client,title='Finance secret',content='Finance forecast code is secret-4455.',visibility='restricted',groups=['finance'])
    add(client,title='Public',content='All employees are issued ID badges.')
    res=client.post('/v1/ask',headers=h('readerkey'),json={'query':'secret-4455'}).json()
    assert all(x['title']!='Finance secret' for x in res['sources'])
    docs=client.get('/v1/documents',headers=h('readerkey')).json()['documents']
    assert [d['title'] for d in docs]==['Public']
    financial=client.post('/v1/ask',headers=h('financekey'),json={'query':'secret-4455'}).json()
    assert any(x['title']=='Finance secret' for x in financial['sources'])
def test_tenant_isolation(client):
    add(client,content='Acme private information solar espresso magnet.')
    res=client.post('/v1/ask',headers=h('globexkey'),json={'query':'solar espresso magnet'}).json()
    assert res['sources']==[]
def test_delete_cascades(client):
    did=add(client).json()['document_id']
    assert client.delete('/v1/documents/'+did,headers=h('globexkey')).status_code==404
    assert client.delete('/v1/documents/'+did,headers=h('adminsecret')).status_code==200
    assert client.post('/v1/ask',headers=h('adminsecret'),json={'query':'disaster recovery'}).json()['sources']==[]
def test_reject_invalid_groups(client):
    assert add(client,visibility='restricted').status_code==422
def test_reject_unsupported_upload(client):
    r=client.post('/v1/documents/upload',headers=h('adminsecret'),files={'file':('bad.exe',b'hello')})
    assert r.status_code==415
def test_upload_markdown(client):
    r=client.post('/v1/documents/upload',headers=h('adminsecret'),files={'file':('policy.md',b'# Policy\nEscalate issues in 24 hours.')})
    assert r.status_code==201
    assert r.json()['chunks']==1
def test_metrics_not_public(client):assert client.get('/metrics').status_code==404
def test_chunk_stability():
    text=' '.join(['alpha beta gamma delta']*200)
    chunks=chunk_text(text)
    assert len(chunks)>1
    assert all(len(c)<=850 for c in chunks)
    assert chunk_text('  ')==[]
def test_embeddings_deterministic():
    assert embed_local('hello world')==embed_local('hello world')
    assert len(embed_local('hello'))==256
def test_search_modes(client):
    add(client,title='Backup policy',content='Daily backup retention is 90 days and the recovery service objective is 4 hours.')
    for mode in ('lexical','vector','hybrid'):
        res=client.post('/v1/ask',headers=h('readerkey'),json={'query':'backup retention', 'mode':mode}).json()
        assert res['sources'][0]['title']=='Backup policy'
def test_no_query_reflection_of_unauthorized_content(client):
    add(client, title='Secret',content='The quantum noodle budget is 999999.', visibility='restricted',groups=['finance'])
    response=client.post('/v1/ask',headers=h('readerkey'),json={'query':'quantum noodle budget'}).json()
    assert '999999' not in str(response)
def test_validation_limits(client):
    assert client.post('/v1/ask',headers=h('readerkey'),json={'query':'hi','k':99}).status_code==422
    assert client.post('/v1/ask',headers=h('readerkey'),json={'query':'hi','mode':'garbage'}).status_code==422
