import os
import asyncio
from aiohttp import ClientSession
import random
import time
import json
import sys
from loguru import logger
from dmutils import determine_if_cmt_public, ConfigParser
from pipeit import *

MIN_INTERVAL = 29

class TaskFail(Exception):
    ...

class TaskAllDone(Exception):
    ...

class Worker:

    def __init__(self, logger):
        self.logger = logger
        self.built_in_cdn_server = 'http://127.0.0.1:8080/'
        self.sessid, self.csrf_token, self.buvid, self.server_url, self.working_mode, self.userid,  self.loglevel, _ = self.init()
        self.logger.remove()
        self.logger.add(sys.stdout, level=self.loglevel)
        if self.server_url[-1] == '/':
            self.server_url = self.server_url[:-1]
        self.logger.info("Worker初始化")
        _msg = "配置文件载入正常" if _ else "配置文件载入失败，初始化配置文件"
        self.logger.info(_msg)
        self.logger.info(f"当前协调服务器地址: {self.server_url}")
        self.logger.info(f"日志级别: {self.loglevel}")
        self.logger.info(f"工作模式: {self.working_mode}")
        self.logger.info(f"用户名: {self.userid}")
        self.logger.debug(f"SESSDATA: {self.sessid}")
        self.logger.debug(f"csrf_token: {self.csrf_token}")
        self.logger.debug(f"buvid: {self.buvid}")
        self.close = False
        self.loop = None

    def init(self):
        file_dir = os.path.dirname(os.path.realpath(__file__))
        cfg_path = os.path.join(file_dir, "config.ini")
        normal_init_flag = True

        try:
            conf = ConfigParser()
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            sessid, csrf_token = secrets['sessid'], secrets['csrf_token']
        except:
            normal_init_flag = False
            sessid, csrf_token = None, None

        assert sessid and csrf_token 

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            buvid = secrets['buvid']
        except:
            normal_init_flag = False
            buvid = self.create_buvid()
            conf.write(cfg_path, {'buvid': buvid})

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            server = secrets['cdn_server']
        except:
            normal_init_flag = False
            server = self.built_in_cdn_server
            conf.write(cfg_path, {'cdn_server': server})

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            mode = secrets['working_mode']
            assert mode in ('auto', 'specified')
        except:
            normal_init_flag = False
            mode = 'auto'
            conf.write(cfg_path, {'working_mode': 'auto'})

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            userid = secrets['userid']
        except:
            normal_init_flag = False
            userid = 'anonymous'
            conf.write(cfg_path, {'userid': 'anonymous'})

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            loglevel = secrets['loglevel']
        except:
            normal_init_flag = False
            loglevel = 'INFO'
            conf.write(cfg_path, {'loglevel': 'INFO'})

        return sessid, csrf_token, buvid, server, mode, userid, loglevel, normal_init_flag

    def create_buvid(self):
        res = ''
        for i in (8,4,4,4,17):
            for j in range(i):
                r = random.randint(0,15)
                res += chr(48 + r) if r < 10 else chr(65 + r - 10)
            else:
                res += '-'
        return res[:-1] + 'infoc'

    async def send_yitiaodanmu(self, session, progress, cid, bvid, msg):

        def check_success(r):
            if r.get("code") == 0 and isinstance(r.get("data", {}).get("dmid"), int) and r.get("data", {}).get("visible") == True:
                return True
            return False

        self.logger.debug("步骤3 - 发送一条弹幕")
        api_url = 'http://api.bilibili.com/x/v2/dm/post'
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
                async with session.post(api_url, data=payload, headers=headers, cookies=cookies) as resp:
                    if resp.status == 200:
                        res = await resp.text()
                        self.logger.debug(f"步骤3反馈 - {res}")
                        res = json.loads(res)
                        if check_success(res):
                            self.logger.debug(f"步骤3成功 - {bvid}:{cid}:{progress}:{msg} - dmid:{res.get('data',{}).get('dmid','dmid')}")
                            return True
                    self.logger.warning(f"步骤3状态码错误 - {resp.status}:{await resp.text()}")
                    await asyncio.sleep(10)
            except:
                raise 
                ...
        else:
            self.logger.debug(f"步骤3失败")
            return False


    async def quest_apply(self, session, query_bvid = None):
        self.logger.debug("步骤1 - 获取")
        if self.working_mode == 'specified':
            assert isinstance(query_bvid, str) # 指定模式下必须输入bvid
        async with session.get(f'{self.server_url}/api/quest-apply', params={'mode': self.working_mode, 'bvid': str(query_bvid)}) as resp:
            if resp.status == 200:
                res = json.loads(await resp.text())
                if res.get('success') == 1:
                    values = res.get('data').values()
                    self.logger.debug(f"步骤1成功 - {values}")
                    return values
                self.logger.warning(f"步骤1失败 - {res.get('detail')}")
            return False

    async def quest_confirm(self, session, bvid, qid, token):
        self.logger.debug("步骤2 - 确认")
        async with session.get(f'{self.server_url}/api/quest-confirm', params={'bvid': bvid, 'qid': qid, 'token': token}) as resp:
            if resp.status == 200:
                res = json.loads(await resp.text())
                if res.get('success') == 1:
                    values = res.get('data').values()
                    self.logger.debug(f"步骤2成功 - {values}")
                    return True
                self.logger.warning(f"步骤2失败 - {res.get('detail')}")
            return False

    async def declare_succeeded(self, session, bvid, qid, token):
        self.logger.debug("步骤5 - 回报")
        async with session.get(f'{self.server_url}/api/quest-success', params={'bvid': bvid, 'qid': qid, 'token': token}) as resp:
            if resp.status == 200:
                res = json.loads(await resp.text())
                if res.get('success') == 1:
                    values = res.get('data').values()
                    self.logger.debug(f"步骤5成功 - {values}")
                    return True
                self.logger.warning(f"步骤5失败 - {res.get('detail')}")
            return False

    async def standard_process(self):

        try:
            self.logger.info("开始一个新的标准投递流程")
            async with ClientSession() as session:
                self.working_mode = 'auto'
                res = await self.quest_apply(session)
                if res == False:
                    raise TaskFail()
                # else
                qid, progress, cid, bvid, msg, token, bias = res
                self.logger.info(f"目标 - {bvid}:{cid}:{progress}:{msg}")
                if bias == 0:
                    raise TaskAllDone()
                await asyncio.sleep(0.5)
                res = await self.quest_confirm(session, bvid, qid, token) 
                if res == False:
                    raise TaskFail()
                await asyncio.sleep(0.5)
                # else
                start_time = time.time()
                res = await self.send_yitiaodanmu(session, progress, cid, bvid, msg)
                if not res: 
                    raise TaskFail()
                # else
                self.logger.debug(f"步骤4 - 等待和检查")
                await asyncio.sleep(20)
                for _, interval in enumerate((5,5,5,5,10,10,10,10,10)):
                    status = await determine_if_cmt_public(session, progress, cid, msg)
                    if status: 
                        self.logger.debug(f"步骤4检查成功")
                        break
                    self.logger.debug(f"步骤4第{_+1}次获取失败")
                    await asyncio.sleep(interval)
                else:
                    raise TaskFail()
                res = await self.declare_succeeded(session, bvid, qid, token)
                if not res:
                    raise TaskFail()
                sleep_time = max(0, MIN_INTERVAL - time.time() + start_time)
                self.logger.info(f"投递成功 - {bvid}:{cid}:{progress}:{msg}")
                if sleep_time > 0:
                    self.logger.info(f"睡眠等待: {'%.2f' % sleep_time}s")
                await asyncio.sleep(sleep_time)
                return 1
        except TaskFail:
            self.logger.info(f"投递失败，流程结束，睡眠")
            await asyncio.sleep(random.randint(10, 20))
            return 2
        except TaskAllDone:
            return 3
        return 2

    async def run_daemon(self):

        fail_count = 0
        while True:
            res = await self.standard_process()
            if res == 3:
                self.logger.info(f"接收到全局结束信号，没有新的弹幕，长睡眠")
                await asyncio.sleep(random.randint(3600, 7200))
                # self.close = True; break
            elif res == 2:
                fail_count += 1
            elif res == 1:
                fail_count = 0
            if fail_count >= 10:
                self.logger.warning(f"连续失败10次投递，设置可能出现问题或SESSDATA过期，请检查相关设置，程序退出")
            await asyncio.sleep(1)

    async def run_start(self):
        self.loop = asyncio.get_running_loop()

        self.loop.create_task(self.run_daemon())
        while True:
            try:
                if self.close:
                    self.logger.info("程序结束")
                    break
                await asyncio.sleep(3)
            except KeyboardInterrupt:
                return

logger.remove()
sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
asyncio.get_event_loop().run_until_complete(Worker(logger).run_start())