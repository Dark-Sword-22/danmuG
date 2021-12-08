import hmac
import random
import logging
import uvicorn
import orjson as json
from hashlib import sha256
from typing import Optional, Literal
from fastapi import FastAPI, Request, Header, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.responses import ORJSONResponse, HTMLResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from dmutils import AsyncIteratorWrapper, git_pull, ConfigParser, EpolledTailFile
from dmdb import *

import platform 
osName = platform.system()
if osName=='Linux':
    import uvloop
    uvloop.install()


file_dir = os.path.dirname(os.path.realpath(__file__))
cfg_path = os.path.join(file_dir, "server_config.ini")
conf = ConfigParser()
conf.read(cfg_path)
secrets = conf.items('secrets')
webhook_secret = secrets['webhook_secret']
trust_list = json.loads(secrets['trust_list'].encode())
dev = json.loads(secrets['dev'].encode())
host = json.loads(secrets['host'].encode())
port = json.loads(secrets['port'].encode())
logsecret = json.loads(secrets['logsecret'].encode())

app = FastAPI(docs_url='/docs' if dev else None, redoc_url=None)
if not dev: 
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trust_list)


sqlite_db = {'drivername': 'sqlite+aiosqlite', 'database': 'sqlite.db'}
engine = create_async_engine(URL.create(**sqlite_db), echo=True, future=True, connect_args={"check_same_thread": False})

error_codes = [
    [{"loc":["query","qid"],"msg":"illegal value, cmt status incorrect","type":"value_error"}], # -1
    [{"loc":["query","bvid"],"msg":"illegal video","type":"value_error"}],                      # -2
    [{"loc":["query","token"],"msg":"token test fail","type":"value_error"}],                   # -3
    [{"loc":["query","bvid"],"msg":"video not found","type":"value_error"}],                    # -4
    [{"loc":["query","bvid"],"msg":"check fail","type":"assertion_error"}],                     # -5
]
for idx in range(len(error_codes)): error_codes[idx] = (-idx-1, {'success':0, 'detail':error_codes[idx]})
else: error_codes = dict(error_codes)

default_logger = logging.getLogger("uvicorn")
msg_core = {}

@app.on_event("startup")
async def startup():
    await scan_and_reload(engine)
    loop = asyncio.get_running_loop()
    loop.create_task(clean_task_daemon(engine, msg_core))

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()

@app.middleware("http")
async def response_logger_hacking(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    resp_body = [_ async for _ in response.__dict__['body_iterator']]
    response.__setattr__('body_iterator', AsyncIteratorWrapper(resp_body))
    if response.status_code == 200:
        _msg = f"Ptime: {round(process_time,3)}s"
        if len(resp_body) == 1:
            try: _msg += f" - {json.loads(resp_body[0].decode('utf-8'))}"
            except: ...
        default_logger.info(_msg)
    return response

@app.get("/api/quest-apply", response_class=ORJSONResponse)
async def get_archive_earliest(mode: Literal["auto", "specified"], bvid: Optional[str] = None) -> dict:
    async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(engine, session, msg_core)
            print("Git push webhook trigered")
            resp = await dal.get_archive_earliest(mode, str(bvid))
            if isinstance(resp, tuple):
                return {'success': 1, 'data': dict(zip(('id', 'progress', 'cid', 'bvid', 'msg', 'token', 'bias'), resp))}
            elif isinstance(resp, bool) and resp == True:
                return {'success': 1, 'data': {'a':1, 'b':2, 'c':3, 'd':4, 'e':5, 'f':6, 'bias':0}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

@app.get("/api/quest-confirm", response_class=ORJSONResponse)
async def client_confirm_quest(bvid: str, qid: int, token: str) -> dict:
    async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(engine, session, msg_core)
            resp = await dal.client_confirm_quest(bvid, qid, token)

            if resp == True:
                return {"success": 1, "data": {"status": "success"}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

@app.get("/api/quest-success", response_class=ORJSONResponse)
async def client_declare_succeeded(bvid: str, qid: int, token: str, wdcr: str = 'anonymous') -> dict:
    if wdcr == 'anonymous':
        wdcr = random.sample(('神秘好哥哥', '缺神'), 1)[0]
    if len(wdcr) > 15:
        wdcr = wdcr[:15]
    async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(engine, session, msg_core)
            resp = await dal.client_declare_succeeded(bvid, qid, token, wdcr)

            if resp == True:
                return {"success": 1, "data": {"status": "success"}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

lu_buffer_man = {datetime.datetime(2002,2,22): []}
@app.get('/api/fetch-superman', response_class=ORJSONResponse)
async def fetch_superman() -> dict:
    last_update_time = tuple(lu_buffer_man.keys())[0]
    current_time = datetime.datetime.now()
    if (current_time - last_update_time).total_seconds() < 120:
        resp = lu_buffer_man[last_update_time]
    else:
        async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
        async with async_session() as session:
            async with session.begin():
                dal = DAL(engine, session, msg_core)
                resp = await dal.fetch_superman()
                lu_buffer_man.clear()
                lu_buffer_man[current_time] = resp
    return resp

lu_buffer_rate = {datetime.datetime(2002,2,22): []}
@app.get('/api/fetch-accomplishment-rate', response_class=ORJSONResponse)
async def fetch_accomplishment_rate() -> dict:
    last_update_time = tuple(lu_buffer_rate.keys())[0]
    current_time = datetime.datetime.now()
    if (current_time - last_update_time).total_seconds() < 600:
        resp = lu_buffer_rate[last_update_time]
    else:
        async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
        async with async_session() as session:
            async with session.begin():
                dal = DAL(engine, session, msg_core)
                resp = await dal.fetch_accomplishment_rate()
                lu_buffer_rate.clear()
                lu_buffer_rate[current_time] = resp
    return resp


pull_stack = []
@app.post("/github-webhook", response_class=ORJSONResponse)
async def github_webhook_activated(req: Request, X_Hub_Signature_256: Optional[str] = Header(None, convert_underscores=True)):
    payload = await req.body()
    res = hmac.compare_digest(hmac.new(webhook_secret.encode(), payload , digestmod = sha256).hexdigest(), X_Hub_Signature_256[7:])
    if res:
        default_logger.info(f"Update pool stack length: {len(pull_stack)}")
        if len(pull_stack) == 0:
            pull_stack.append(None)
            while pull_stack:
                default_logger.info("Git push webhook trigered")
                await git_pull(asyncio.get_running_loop())
                default_logger.info("Git pulled")
                await scan_and_reload(engine)
                default_logger.info("Engine finish update")
                pull_stack.pop()
        else:
            while len(pull_stack) > 1:
                pull_stack.pop()
            pull_stack.push(None)
        default_logger.debug(f"Send response, pool stack length: {len(pull_stack)}")
    return {'success': 0, 'data': {'assertion result': res}}

@app.get("/log/danmuG")
async def html_log_danmug(token: str = ''):
    if not hmac.compare_digest(token, logsecret):
        return HTTPException(status_code=403, detail="403 Forbidden")
    async with aiofiles.open(os.path.abspath('../templates/log.html'), mode='r') as f:
        html = await f.read()
        return HTMLResponse(html)

@app.websocket('/ws/danmuG')
async def ws_log_danmug(websocket: WebSocket, token: str = ''):
    file_path = os.path.abspath('../log_out.txt')
    async_reader = EpolledTailFile(file_path)
    await websocket.accept()
    try:
        async_reader.start_listen()
        while True:
            line = await async_reader.upstream()
            await websocket.send_text(f"Message text was: {line}")
    except:
        ...
    finally:
        async_reader.close()

@app.get("/log/server")
async def html_log_danmug(token: str = ''):
    if not hmac.compare_digest(token, logsecret):
        return HTTPException(status_code=403, detail="403 Forbidden")
    return HTMLResponse(html)

@app.websocket('/ws/server')
async def ws_log_danmug(websocket: WebSocket, token: str = ''):
    file_path = os.path.abspath('../log_out.txt')
    async_reader = EpolledTailFile('www.google.com')
    await websocket.accept()
    try:
        async_reader.start_listen()
        while True:
            line = await async_reader.upstream()
            await websocket.send_text(f"Message text was: {line}")
    except:
        ...
    finally:
        async_reader.close()


if __name__ == '__main__':
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    log_config["formatters"]["access"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    uvicorn.run("dmserver:app", port=port, host=host, log_config=log_config) 