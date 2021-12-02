import uvicorn
from fastapi import FastAPI
from dmdb import *
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

app = FastAPI()

msg_core = {}
sqlite_db = {'drivername': 'sqlite+aiosqlite', 'database': 'test.db'}
engine = create_async_engine(URL.create(**sqlite_db), echo=True, future=True)


@app.on_event("startup")
async def startup():
    await scan_and_init(engine)
    loop = asyncio.get_running_loop()
    loop.create_task(clean_task_daemon(engine, msg_core))

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()


@app.get("/api/quest-apply")
async def get_archive_earliest(bvid: str) -> dict:
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(session)
            resp = await dal.get_archive_earliest(bvid)
            if isinstance(resp, tuple):
                return dict(zip(('id', 'progress', 'cid', 'bvid', 'msg'), resp))
            elif resp == -3:
                ...
    return {"detail":[{"loc":["query","bvid"],"msg":"video not found","type":"value_error"}]}

@app.get("/api/quest-confirm")
async def client_confirm_quest(bvid: str, id: int) -> dict:
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(session)
            await dal.get_archive_earliest(bvid) # 
            resp = await dal.client_confirm_quest(bvid, id)
            if resp == True:
                return {"status": "success"}
            elif resp == -1:
                return {"detail":[{"loc":["query","id"],"msg":"illegal value, cmt status incorrect","type":"value_error"}]}
            elif resp == -2:
                return {"detail":[{"loc":["query","bvid"],"msg":"illegal video","type":"value_error"}]}
            return {}

@app.get("/api/quest-success")
async def client_confirm_quest(bvid: str, id: int, wdcr: str = '神秘好哥哥') -> dict:
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            dal = DAL(session)
            await dal.get_archive_earliest(bvid)
            resp = await dal.client_declare_succeeded(bvid, id, wdcr)
            if resp == True:
                return {"status": "success"}
            elif resp == -6:
                return {"detail":[{"loc":["query","bvid"],"msg":"check fail","type":"assertion_error"}]}
            elif resp == -9 or resp == -12:
                return {"detail":[{"loc":["query","id"],"msg":"Unexplained error","type":"internal_error"}]}
            return {}

if __name__ == '__main__':
    uvicorn.run("dmserver:app", port=8080, host='127.0.0.1')