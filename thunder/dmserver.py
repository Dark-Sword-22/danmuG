import uvicorn
from fastapi import FastAPI
from dmdb import *
from typing import Optional, Literal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import random

app = FastAPI()

msg_core = {}
sqlite_db = {'drivername': 'sqlite+aiosqlite', 'database': 'test.db'}
engine = create_async_engine(URL.create(**sqlite_db), echo=True, future=True)

error_codes = [
    [{"loc":["query","qid"],"msg":"illegal value, cmt status incorrect","type":"value_error"}], # -1
    [{"loc":["query","bvid"],"msg":"illegal video","type":"value_error"}],                      #-2
    [{"loc":["query","token"],"msg":"token test fail","type":"value_error"}],                   #-3
    [{"loc":["query","bvid"],"msg":"video not found","type":"value_error"}],                    #-4
    [{"loc":["query","bvid"],"msg":"check fail","type":"assertion_error"}],                     # -5
]
for idx in range(len(error_codes)): error_codes[idx] = (-idx-1, {'success':0, 'detail':error_codes[idx]})
else: error_codes = dict(error_codes)


@app.on_event("startup")
async def startup():
    await scan_and_init(engine)
    loop = asyncio.get_running_loop()
    loop.create_task(clean_task_daemon(engine, msg_core))

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()

@app.get("/api/quest-apply")
async def get_archive_earliest(mode: Literal["auto", "specified"], bvid: str) -> dict:
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(session, msg_core)
            resp = await dal.get_archive_earliest(mode, bvid)

            if isinstance(resp, tuple):
                return {'success': 1, 'data': dict(zip(('id', 'progress', 'cid', 'bvid', 'msg', 'token', 'bias'), resp))}
            elif isinstance(resp, bool) and resp == True:
                return {'success': 1, 'data': {1:1, 2:2, 3:3, 4:4, 5:5, 6:6, 'bias':0}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

@app.get("/api/quest-confirm")
async def client_confirm_quest(bvid: str, qid: int, token: str) -> dict:
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(session, msg_core)
            resp = await dal.client_confirm_quest(bvid, qid, token)

            if resp == True:
                return {"success": 1, "data": {"status": "success"}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

@app.get("/api/quest-success")
async def client_declare_succeeded(bvid: str, qid: int, token: str, wdcr: str = 'anonymous') -> dict:
    if wdcr == 'anonymous':
        wdcr = random.sample(('神秘好哥哥', '缺神'), 1)[0]
    if len(wdcr) > 15:
        wdcr = wdcr[:15]
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(session, msg_core)
            resp = await dal.client_declare_succeeded(bvid, qid, token, wdcr)

            if resp == True:
                return {"success": 1, "data": {"status": "success"}}
            elif isinstance(resp, int):
                return error_codes[resp]
            return {}

if __name__ == '__main__':
    uvicorn.run("dmserver:app", port=8080, host='127.0.0.1')