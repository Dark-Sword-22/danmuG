import os
import time
import hmac
import random
import asyncio
import uvicorn
import orjson as json
from aiohttp import ClientSession
from fastapi import FastAPI, Request, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.responses import ORJSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from dmutils import ConfigParser
from ThreadPoolExecutorPlus import ThreadPoolExecutor
from dmutils import captcha_cleaner, render_new_catpcha, captcha_str_filter, ws_coro_heartbeat
from slowapi import RateLimiter

file_dir = os.path.dirname(os.path.realpath(__file__))
cfg_path = os.path.join(file_dir, "server_config.ini")
conf = ConfigParser()
# conf.read(cfg_path)
# secrets = conf.items('secrets')
# trust_list = json.loads(secrets['trust_list'].encode())
# dev = json.loads(secrets['dev'].encode())
dev = True;trust_list = []


executor = [None, ]

app = FastAPI(docs_url='/docs' if dev else None, redoc_url=None)
origins = [
    "*",
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:8080",
]
if not dev: 
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trust_list)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

captcha_dict = {}
b_headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-encoding': 'gzip, deflate',
    'accept-language': 'zh-CN,zh;q=0.9',
    'origin': 'https://www.bilibili.com',
    'referer': 'https://www.bilibili.com/?spm_id_from={0}.{1}.0.0',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': "Windows",
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36',
}


@app.on_event("startup")
async def startup():
    RateLimiter().porter_run_serve()
    asyncio.create_task(captcha_cleaner(captcha_dict))


@app.get("/bilibili-login", response_class=ORJSONResponse)
@RateLimiter(20, 10)
async def pre_captcha(dynamic_string: str):
    if len(dynamic_string) != 8 or len(captcha_dict) > 100:
        return HTTPException(status_code=422, detail="403 Forbidden")

    _executor = executor[0]
    loop = asyncio.get_running_loop()
    try:
        captcha_id, create_time, orn_captcha, captcha_base64 = await loop.run_in_executor(_executor, render_new_catpcha) # 3ms
        orn_captcha = captcha_str_filter(orn_captcha)
        captcha_dict[captcha_id] = (orn_captcha, create_time)
        print(captcha_dict)
        return {'success': 1, "data": {'key': captcha_id, 'image': captcha_base64, 'msg': ''}}
    except Exception as e:
        return {'success': 0, "data": {'msg': f"{type(e)}: {str(e)}"}}

from loguru import logger
@app.websocket('/ws/bilibili-login')
async def ws_log_danmug(websocket: WebSocket, captcha_id: str = '', user_string: str = ''):
    orn_captcha = captcha_dict.get(captcha_id, [None, ])[0]
    if orn_captcha is None or not hmac.compare_digest(orn_captcha, captcha_str_filter(user_string)):
        return HTTPException(status_code=403, detail="403 Forbidden")
    del captcha_dict[captcha_id] # 释放占用

    await websocket.accept()

    b_headers_cp = b_headers.copy()
    b_headers_cp['referer'] = b_headers_cp['referer'].format(random.randint(300,400), random.randint(100,999))
    async with ClientSession() as session:
        async with session.get('https://passport.bilibili.com/qrcode/getLoginUrl', headers = b_headers_cp) as resp:
            back_content = None
            if resp.status == 200:
                back_content = await resp.text()

        if back_content is None:
            await websocket.send_json({'success': 0, "data": {'msg': "向B站发送的请求失败了-1 (・ˍ・*)"}});return
        try:
            logger.info(back_content)
            back_content = json.loads(back_content)
            if back_content['code'] != 0:
                await websocket.send_json({'success': 0, "data": {'msg': "向B站发送的请求失败了-2 (・ˍ・*)"}});return
            passport_url = back_content['data']['url']
            oauthKey = back_content['data']['oauthKey']
            assert len(passport_url) == 87
            assert len(oauthKey) == 32
        except Exception as e:
            await websocket.send_json({'success': 0, "data": {'msg': f"{type(e)}: {str(e)}"}}); return

        await websocket.send_json({'success': 1, "data": {'msg': "url", "url": passport_url}})
        st_call_time = time.time()
        payload = {'oauthKey': oauthKey}
        while True:
            await asyncio.sleep(2)
            cur_time = time.time()
            if (cur_time - st_call_time) > 175:
                await websocket.send_json({'success': 0, "data": {'msg': "二维码过期"}}); return
            try:
                async with session.post('http://passport.bilibili.com/qrcode/getLoginInfo', headers = b_headers_cp, data = payload) as resp:
                    if resp.status != 200:
                        continue
                    carry = json.loads(await resp.text())
                    flag1 = carry.get('status')
                    flag2 = carry.get('data')
                    if flag1 == True:
                        await websocket.send_json({'success': 1, "data": {'msg': 'success', 'sess':resp.cookies.get("SESSDATA").value, 'csrf':resp.cookies.get("bili_jct").value}}); return
                    if flag2 not in (-4, -5):
                        await websocket.send_json({'success': 0, "data": {'msg': "二维码过期"}}); return
                    # else 
                    await websocket.send_json({'success': 0, "data": {'msg': "heart beat"}})
            except Exception as e:
                raise e
                await websocket.send_json({'success': 0, "data": {'msg': f"{type(e)}: {str(e)}"}}); return



    
    
    




if __name__ == '__main__':
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    log_config["formatters"]["access"]["fmt"] = "[%(asctime)s] | %(levelname)s | %(message)s"
    with ThreadPoolExecutor(max_workers=16) as ex:
        ex.set_daemon_opts(min_workers=5)
        executor[0] = ex
    uvicorn.run("bilibili_login_proxy_server:app", port=8080, host='0.0.0.0', log_config=log_config, reload=dev) 



