import hmac
import random
import logging
import uvicorn
import orjson as json
from hashlib import sha256
from aiohttp import ClientSession
from typing import Optional, Literal
from fastapi import FastAPI, Request, Header, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.responses import ORJSONResponse, HTMLResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from dmutils import AsyncIteratorWrapper, git_pull, ConfigParser, EpolledTailFile, ws_coro_main, ws_coro_heartbeat
from dmdb import *

import platform 
osName = platform.system()
if osName=='Linux':
    import uvloop
    uvloop.install()

'''
配置于127.0.0.1:2222单线程异步服务器，前面肯定还要接nginx的，配合limit_req_zone总体处于性能堪用水平。

配置文件范例: 

# server_config.ini
[secrets]
webhook_secret=example-token
trust_list=["example.com","*.example.com"]
dev=false
host="127.0.0.1"
port=2222
logsecret="example-token-2"
'''

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
engine = create_async_engine(URL.create(**sqlite_db), echo=False, future=True, connect_args={"check_same_thread": False})

# 异常表
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
    '''
    初始扫描服务器，结束时关闭连接池
    '''
    await scan_and_reload(engine)
    loop = asyncio.get_running_loop()
    loop.create_task(clean_task_daemon(engine, msg_core))

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()

@app.middleware("http")
async def response_logger_hacking(request: Request, call_next):
    '''
    接管uvicorn的default logger
    '''
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
    '''
    一个投递流程分为三步， client 先获取任务，再确认要提交的任务，最后确认已经提交成功。
    其对应的后端 status 为 0,1,3
    目前这个 handler 处理的是第一步，可以指定 BVID 或者选择自动获取最新视频的弹幕
    '''
    async with async_session() as session:
        async with session.begin():
            dal = DAL(engine, session, msg_core)
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
    '''
    见 get_archive_earliest
    确认任务并修改状态至 1
    '''
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
    '''
    见 get_archive_earliest
    检查投递成功并更新状态。限制最大用户名长度作为防止xss的另一层手段。
    如果用户为匿名则默认从两个用户名中选一个。
    '''
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
    '''
    静态页面更新用 actions 更新时向后端请求最新贡献榜单。
    '''
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
    '''
    静态页面更新用 actions 更新时向后端请求视频投稿完成度。
    '''
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

vspat_1 = re.compile('''VERSION = ('|")[\d]+\.[\d]+\.[\d]+('|")''')
vspat_2 = re.compile('[\d]+\.[\d]+\.[\d]+')
lu_buffer_ver = {datetime.datetime(2002,2,22): ''}
@app.get('/api/latest-client-version', response_class=ORJSONResponse)
async def latest_client_version() -> dict:
    last_update_time = tuple(lu_buffer_ver.keys())[0]
    current_time = datetime.datetime.now()
    if (current_time - last_update_time).total_seconds() < 600:
        resp = lu_buffer_ver[last_update_time]
    else:
        try:
            async with ClientSession() as session:
                async with session.get('https://raw.githubusercontent.com/Dark-Sword-22/danmuG/main/thunder/dmclient.py') as query:
                    assert query.status == 200
                    script_raw = await query.text()
                    remote_version = vspat_2.search(vspat_1.search(script_raw).group()).group()
                    resp = {'success': True, 'version': remote_version}
                    lu_buffer_ver.clear()
                    lu_buffer_ver[current_time] = resp
        except:
            resp = {'success': False, 'version': None}  
    return resp

pull_stack = []
@app.post("/github-webhook", response_class=ORJSONResponse)
async def github_webhook_activated(req: Request, X_Hub_Signature_256: Optional[str] = Header(None, convert_underscores=True)):
    '''
    用于接受 github push 钩子事件。使 data 中的数据一直保持最新，并触发更新模块，数据库也会对应进行增删。
    设置一个更新栈，因为数次积累更新实际只需要触发一次pull，所以排除掉积累的更新请求。栈中保存False则只会更新数据，True则同步刷新db
    '''
    payload = await req.body()
    res = hmac.compare_digest(hmac.new(webhook_secret.encode(), payload , digestmod = sha256).hexdigest(), X_Hub_Signature_256[7:])
    if res:
        # 判断是否是bot更新，不接受bot更新后产生的推流.
        try:
            data = json.loads(payload.decode('utf-8'))
            pass_flag = 'Render' in data["commits"][0]["message"]
        except:
            pass_flag = False
        default_logger.info(f"Update pool stack length: {len(pull_stack)}")
        if len(pull_stack) == 0:
            pull_stack.append(not pass_flag)
            while pull_stack:
                refresh_db_flag = pull_stack.pop()
                default_logger.info("Git push webhook trigered")
                await git_pull(asyncio.get_running_loop())
                default_logger.info("Git pulled")
                if refresh_db_flag:
                    await scan_and_reload(engine)
                    default_logger.info("Engine finish update")
                else:
                    default_logger.info("Engine update passed")
        else:
            has_refresh_db_flag = False
            while len(pull_stack) > 1:
                if pull_stack.pop():
                    has_refresh_db_flag = True
            pull_stack.push(has_refresh_db_flag or (not pass_flag))
        default_logger.debug(f"Send response, pool stack length: {len(pull_stack)}")
    return {'success': 0, 'data': {'assertion result': res}}

@app.get("/log/danmuG")
async def html_log_danmug(token: str = ''):
    '''
    查看系统日志的 html 前端，做了简单的 token 认证，配合 https 问题不是很大。
    '''
    if not hmac.compare_digest(token, logsecret):
        return HTTPException(status_code=403, detail="403 Forbidden")
    async with aiofiles.open(os.path.abspath('../templates/htmllog.html'), mode='r') as f:
        html = await f.read()
        return HTMLResponse(html.replace("{{service_name}}", "danmuG").replace("{{secret}}", token))

@app.websocket('/ws/danmuG')
async def ws_log_danmug(websocket: WebSocket, token: str = ''):
    '''
    查看系统日志的后端， ws 实时推流理论上结果应与 ssh tail -f 输出一致。
    维护 tail-f 的 fd event_read 的 selector 放在另一线程池里。
    这里额外加入一个 ws 撞针，如果没有撞针的话，执行顺序是先获取更新再发送 ws ，
    在 fd 没有更新的时候获取线程会一直 pending ，而 fastapi 的 ws 断连本身不会异常
    只有向断连 ws 继续发送时才会报异常。导致没有撞针时即使断连占用的资源也无法释放。
    当然 epoll 本身也要 timeout 否则会一直在挂起队列上。
    '''
    if not hmac.compare_digest(token, logsecret):
        return HTTPException(status_code=403, detail="403 Forbidden")
    file_path = os.path.abspath('../log_out.txt')
    async_reader = EpolledTailFile(file_path)
    await websocket.accept()
    try:
        async_reader.start_listen()
        await asyncio.gather(ws_coro_heartbeat(websocket), ws_coro_main(async_reader, websocket))
    except:
        ...
    finally:
        async_reader.close()

@app.get("/log/server")
async def html_log_danmug(token: str = ''):
    '''
    重复逻辑，见 html_log_danmug 和 ws_log_danmug 部分
    '''
    if not hmac.compare_digest(token, logsecret):
        return HTTPException(status_code=403, detail="403 Forbidden")
    async with aiofiles.open(os.path.abspath('../templates/htmllog.html'), mode='r') as f:
        html = await f.read()
        return HTMLResponse(html.replace("{{service_name}}", "server").replace("{{secret}}", token))
    return HTMLResponse(html)

@app.websocket('/ws/server')
async def ws_log_danmug(websocket: WebSocket, token: str = ''):
    '''
    重复逻辑，见 html_log_danmug 和 ws_log_danmug 部分
    '''
    if not hmac.compare_digest(token, logsecret):
        return HTTPException(status_code=403, detail="403 Forbidden")
    file_path = os.path.abspath('../slog_out.txt')
    async_reader = EpolledTailFile(file_path)
    await websocket.accept()
    try:
        async_reader.start_listen()
        await asyncio.gather(ws_coro_heartbeat(websocket), ws_coro_main(async_reader, websocket))
    except:
        ...
    finally:
        async_reader.close()


if __name__ == '__main__':
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    log_config["formatters"]["access"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    uvicorn.run("dmserver:app", port=port, host=host, log_config=log_config) 