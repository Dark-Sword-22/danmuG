import os
import asyncio
from aiohttp import ClientSession
import random
import time
import json
from loguru import logger
from pipeit import *

class ConfigParser:

    def __init__(self):
        self.text = ''

    def read(self, cfg_path):
        self.text = Read(cfg_path)
        return self

    def write(self, cfg_path, data):
        self.text = Read(cfg_path).strip()
        self.text += '\n'
        for k, v in data.items():
            self.text += f"{k}={v}\n"
        Write(cfg_path, self.text)

    def getsession(self, session):
        x = self.text[self.text.index(f"[{session}]\n") + len(session) + 3:]
        try:
            x2 = x[:x.index('[')]
        except:
            x2 = ''
        return  (x + x2).strip()

    def items(self, session):
        _session_cont = self.getsession(session)
        _session_cont = _session_cont.split('\n') | Map(lambda x:x.strip()) | Filter(lambda x:x!='') | list
        res = {}
        for _ in _session_cont:
            res[_[:_.index('=')]] = _[_.index('=')+1:]
        return res

class Worker:

    def __init__(self):
        self.sessid, self.csrf_token, self.buvid = self.init()
        self.loop = None

    def init(self):
        file_dir = os.path.dirname(os.path.realpath(__file__))
        cfg_path = os.path.join(file_dir, "config.ini")

        try:
            conf = ConfigParser()
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            sessid, csrf_token = secrets['sessid'], secrets['csrf_token']
        except:
            sessid, csrf_token = None, None

        assert sessid and csrf_token 

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            buvid = secrets['buvid']
        except:
            buvid = self.create_buvid()
            conf.write(cfg_path, {'buvid': buvid})

        return sessid, csrf_token, buvid

    def create_buvid(self):
        res = ''
        for i in (8,4,4,4,17):
            for j in range(i):
                r = random.randint(0,15)
                res += chr(48 + r) if r < 10 else chr(65 + r - 10)
            else:
                res += '-'
        return res[:-1] + 'infoc'

    async def send_yitiaodanmu(self, session, bvid, cid, msg, progress):

        def check_success(text):
            r = json.loads(text)
            if r.get("code") == 0 and isinstance(r.get("data", {}).get("dmid"), int) and r.get("data", {}).get("visible") == True:
                return True
            return False

        url = 'http://api.bilibili.com/x/v2/dm/post'
        headers = {
            ':authority': 'api.bilibili.com',
            ':method': 'POST',
            ':path': '/x/v2/dm/post',
            ':scheme': 'https',
            'accept': '*/*',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://www.bilibili.com',
            'referer': f'https://www.bilibili.com/video/{bvid}',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="96", "Google Chrome";v="96"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36',
        }
        cookies = {
            'SESSDATA': self.sessid,
            'bili_jct': self.csrf_token,
            'buvid3': self.buvid,
            'buvid_fp': self.buvid,
            'buvid_fp_p': self.buvid,
        }
        payload = {
            'type': '1',
            'oid': cid,
            'msg': msg,
            'bvid': bvid,
            'progress': progress,
            'color': '16777215',
            'fontsize': '25',
            'pool': '0',
            'mode': '1',
            'rnd': str(int(time.time() * 1e6)),
            'plat': '1',
            'csrf': self.csrf_token,
        }
        for _ in range(2):
            try:
                async with session.post(url, data=payload, headers=headers, cookies=cookies) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        if check_success(text):
                            return True
                    await asyncio.sleep(10)
            except:
                ...
        else:
            return False


    async def standard_process(self):

        async with ClientSession() as session:
            bvid, cid, msg, progess = await self.query_ask(session)
            await self.query_confirm(session)
            res = await self.send_yitiaodanmu(session, bvid, cid, msg, progress)
            if not res:
                await asyncio.sleep(30)
                return False
            await asyncio.sleep(20)
            for _ in range(5):
                status = await self.ask_if_uploaded(session)
                if status:
                    break
                await asyncio.sleep(3)
            else:
                for _ in range(10):
                    status = await self.ask_if_uploaded(session)
                    await asyncio.sleep(5)
                    if status:
                        break
                else:
                    return False
            await self.declare_success(session)
            await asyncio.sleep(5)


    async def run_start(self):
        self.loop = asyncio.get_running_loop()

        

        while True:
            try:
                await asyncio.sleep(3600)
            except KeyboardInterrupt:
                return





















asyncio.get_event_loop().run_until_complete(Worker().run_start())