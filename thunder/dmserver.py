import hmac
import random
import logging
import uvicorn
import orjson as json
from hashlib import sha256
from typing import Optional, Literal
from fastapi import FastAPI, Request, Header
from fastapi.responses import ORJSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from dmutils import AsyncIteratorWrapper, load_webhook_secret
from dmdb import *


app = FastAPI()
# app.add_middleware(
#     TrustedHostMiddleware, allowed_hosts=["example.com", "*.example.com"]
# )


sqlite_db = {'drivername': 'sqlite+aiosqlite', 'database': 'test.db'}
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

webhook_secret = load_webhook_secret()

@app.on_event("startup")
async def startup():
    await scan_and_init(engine)
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
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(engine, session, msg_core)
            resp = await dal.get_archive_earliest(mode, str(bvid))

            if isinstance(resp, tuple):
                return {'success': 1, 'data': dict(zip(('id', 'progress', 'cid', 'bvid', 'msg', 'token', 'bias'), resp))}
            elif isinstance(resp, bool) and resp == True:
                return {'success': 1, 'data': {1:1, 2:2, 3:3, 4:4, 5:5, 6:6, 'bias':0}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

@app.get("/api/quest-confirm", response_class=ORJSONResponse)
async def client_confirm_quest(bvid: str, qid: int, token: str) -> dict:
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
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
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(engine, session, msg_core)
            resp = await dal.client_declare_succeeded(bvid, qid, token, wdcr)

            if resp == True:
                return {"success": 1, "data": {"status": "success"}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

@app.get('/api/fetch-superman', response_class=ORJSONResponse)
async def fetch_superman() -> dict:
    ...


@app.post("/github-webhook", response_class=ORJSONResponse)
async def github_webhook_activated(req: Request, X_Hub_Signature_256: Optional[str] = Header(None, convert_underscores=True)):
    payload = await req.body()
    res = hmac.compare_digest(hmac.new('secret'.encode(), payload , digestmod = sha256).hexdigest(), X_Hub_Signature_256[8:])
    if res:
        ...
    return {'success': 0, 'data': {'assertion result': res}}


if __name__ == '__main__':
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    log_config["formatters"]["access"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    uvicorn.run("dmserver:app", port=8080, host='127.0.0.1', log_config=log_config) 