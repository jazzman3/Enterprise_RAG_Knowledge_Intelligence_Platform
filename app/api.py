from __future__ import annotations
import os, re, secrets, time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from .core import Store, answer_extractive, answer_llm

requests_total=Counter('rag_requests_total','RAG requests',['route','status'])
search_latency=Histogram('rag_search_seconds','Retrieval time in seconds',buckets=(.005,.01,.025,.05,.1,.25,.5,1,2,5,10))

def current_store():
    return Store(os.getenv('DATABASE_PATH','./data/rag.db'))

class Principal(BaseModel):
    tenant: str
    user: str
    groups: list[str]
    role: str

def auth(x_api_key: str|None=Header(default=None)) -> Principal:
    # Header keys mapped to principals server-side; never trust tenant/group claims from client.
    raw=os.getenv('RAG_API_KEYS','')
    # format key|tenant|username|role|comma-separated-groups;semicolons delimit entries
    for item in raw.split(';'):
        fields=item.strip().split('|')
        if len(fields)==5 and x_api_key is not None and secrets.compare_digest(fields[0],x_api_key):
            return Principal(tenant=fields[1],user=fields[2],role=fields[3],groups=[g for g in fields[4].split(',') if g])
    raise HTTPException(401,'Invalid or missing API key')

def admin(p:Principal=Depends(auth)):
    if p.role not in ('admin','editor'): raise HTTPException(403,'Editor role required')
    return p

class DocumentIn(BaseModel):
    title: str=Field(min_length=1,max_length=180)
    content: str=Field(min_length=1,max_length=180000)
    visibility: Literal['all','restricted']='all'
    groups: list[str]=Field(default_factory=list,max_length=30)

class AskIn(BaseModel):
    query: str=Field(min_length=1,max_length=2000)
    k: int=Field(default=5,ge=1,le=10)
    mode: Literal['hybrid','lexical','vector']='hybrid'

@asynccontextmanager
async def lifespan(app:FastAPI):
    current_store()
    yield

app=FastAPI(title='Enterprise RAG Knowledge Intelligence Platform',version='1.0.0',lifespan=lifespan)
origins=[x for x in os.getenv('CORS_ORIGINS','http://localhost:8080').split(',') if x]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','DELETE'],allow_headers=['X-API-Key','Content-Type'])

@app.middleware('http')
async def stats(request:Request,call_next):
    start=time.perf_counter()
    try:
        response=await call_next(request)
        requests_total.labels(request.url.path,str(response.status_code)).inc()
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Cache-Control']='no-store'
        return response
    except Exception:
        requests_total.labels(request.url.path,'500').inc();raise

@app.get('/healthz')
def health():return {'status':'ok'}
@app.get('/metrics')
def metrics():
    if os.getenv('EXPOSE_METRICS','false').lower()!='true': raise HTTPException(404,'Not found')
    return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

@app.post('/v1/documents',status_code=201)
def ingest(req:DocumentIn,p:Principal=Depends(admin)):
    try:return current_store().ingest(p.tenant,req.title,req.content,req.visibility,req.groups,p.user)
    except ValueError as e:raise HTTPException(422,str(e))

@app.post('/v1/documents/upload',status_code=201)
async def upload(file:UploadFile=File(...),visibility:str=Form('all'),groups:str=Form(''),p:Principal=Depends(admin)):
    data=await file.read(200001)
    if len(data)>200000:raise HTTPException(413,'File too large')
    name=Path(file.filename or 'document').name
    suffix=Path(name).suffix.lower()
    if suffix not in ('.txt','.md','.pdf'):raise HTTPException(415,'Only TXT, Markdown, and PDF')
    if suffix=='.pdf':
        from pypdf import PdfReader
        from io import BytesIO
        try:
            pdf=PdfReader(BytesIO(data),strict=False)
            if len(pdf.pages)>80:raise HTTPException(413,'PDF page limit exceeded')
            content='\n'.join((page.extract_text() or '') for page in pdf.pages)
        except HTTPException:raise
        except Exception:raise HTTPException(422,'PDF cannot be parsed')
    else:
        try: content=data.decode('utf-8')
        except UnicodeDecodeError:raise HTTPException(422,'Must be valid UTF-8')
    try:return current_store().ingest(p.tenant,name,content,visibility,[x.strip() for x in groups.split(',') if x.strip()],p.user)
    except ValueError as e:raise HTTPException(422,str(e))

@app.get('/v1/documents')
def docs(p:Principal=Depends(auth)):
    return {'documents':current_store().docs(p.tenant,p.groups)}

@app.delete('/v1/documents/{document_id}')
def delete(document_id:str,p:Principal=Depends(admin)):
    if not current_store().delete(p.tenant,document_id,p.user):raise HTTPException(404,'Document not found')
    return {'deleted':True}

@app.post('/v1/ask')
def ask(req:AskIn,p:Principal=Depends(auth)):
    start=time.perf_counter();store=current_store()
    hits=store.search(p.tenant,req.query,p.groups,req.k,req.mode)
    duration=time.perf_counter()-start;search_latency.observe(duration)
    store.log(p.tenant,p.user,'ask',req.query[:160])
    if os.getenv('ANSWER_PROVIDER','extractive')=='openai':
        try:answer=answer_llm(req.query,hits);provider='openai'
        except Exception:raise HTTPException(502,'Answer service unavailable')
    else:answer=answer_extractive(req.query,hits);provider='extractive'
    return {'answer':answer,'provider':provider,'retrieval_ms':round(duration*1000,3),
      'sources':[{'citation':f'[{i}]','document_id':h.document_id,'chunk_id':h.chunk_id,'title':h.title,'excerpt':h.content[:900],'score':round(h.score,5)} for i,h in enumerate(hits,1)]}
