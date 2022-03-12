import os
import asyncio
import signal
import random
import time
import json
import sys
import re
import requests
from loguru import logger
from aiohttp import ClientSession
from hyper.contrib import HTTP20Adapter
from dmutils import determine_if_cmt_public, ConfigParser
from pipeit import *

VERSION = '1.0.10'
MIN_INTERVAL = 28

class TaskFail(Exception):
    ...

class TaskFailnoSleep(Exception):
    ...

class TaskAllDone(Exception):
    ...

class Worker:

    def __init__(self, logger):
        self.logger = logger
        self.built_in_cdn_server = 'https://dog.464933.xyz/'
        self.sessid, self.csrf_token, self.buvid, self.server_url, self.working_mode, self.userid,  self.loglevel, self.worktime, self.proxy , _ = self.init()
        self.sleeptime = 24 - self.worktime
        while self.server_url[-1] == '/':
            self.server_url = self.server_url[:-1]
        self.logger.add(sys.stdout, level=self.loglevel)
        self.logger.info("Worker初始化")
        _msg = "配置文件载入正常" if _ else "配置文件载入失败，初始化配置文件"
        self.logger.info(_msg)
        self.logger.info(f"弹幕投稿器版本: {VERSION}")
        _remote_version, _error = self.remote_version()
        if _remote_version == None:
            self.logger.warning("远端版本号获取失败，程序可能出现某种错误")
            self.logger.warning(f"错误信息: {type(_error)}:{str(_error)}")
            input("")
            sys.exit(1)
        elif _remote_version == VERSION:
            self.logger.info(f"侦测到当前客户端版本为最新")
        else:
            self.logger.warning(f"侦测到远程版本号为: {_remote_version} ，与本地不符，您可能需要进行更新")
        self.logger.info(f"当前协调服务器地址: {self.server_url}")
        self.logger.info(f"代理地址: {self.proxy}")
        self.logger.info(f"日志级别: {self.loglevel}")
        self.logger.info(f"工作模式: {self.working_mode}")
        self.logger.info(f"工作/睡眠时长: {self.worktime}/{self.sleeptime}h")
        self.logger.info(f"用户名: {self.userid}")
        self.logger.debug(f"SESSDATA: {self.sessid}")
        self.logger.debug(f"csrf_token: {self.csrf_token}")
        self.logger.debug(f"buvid: {self.buvid}")
        self._last_sigint_time = time.time()
        self.workflag = True
        self.global_sleep_daemon = None
        self.close = False
        self.fail_count = 0
        self.wait_closed = asyncio.Event()
        self.loop = None
        if self.working_mode == 'specified':
            self.logger.info("请输入你希望投稿的视频链接（完整连接，不区分http和https），")
            self.logger.info("之后按回车继续。")
            self.logger.info("| 请注意，由于协调服务器仅缓存近期数据，距今22天以前上传的视频地址可能无法工作 |")
            inp = input()
            inp = re.search('/BV[a-zA-Z0-9]+', inp)
            if inp:
                self.query_bvid = inp.group()[1:]
                assert 8 <= len(self.query_bvid) <= 16
                self.logger.info(f"你输入的视频BV号为: {self.query_bvid}")
            else:
                self.logger.warning("视频编号提取失败，请检查输入链接，程序结束。")
        else:
            self.query_bvid = None
        if self.proxy != False:
            input("由于Python打包bug，打包版本下无法使用代理，请参考使用说明中的代理部分直接调用源码，程序退出")
            sys.exit(1)


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
            sessid, csrf_token = '', ''

        def check_failed():
            input("身份信息校验失败，按任意键退出"); sys.exit(1)

        if not (28 <= len(sessid) <= 34) or len(csrf_token) != 32: # 如果出现错误代表获取到的数据不合法 
            check_failed()
        else:
            pat = re.match('[a-zA-Z0-9]{6,12}(%2C|,)[\d]{10,12}(%2C|,)[A-Za-z0-9%\*]{6,12}', sessid)
            if pat == None:
                check_failed()
            if ',' in sessid:
                sessid = sessid.replace(',', '%2C')

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

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            worktime = secrets['worktime']
            assert worktime.isdigit()
            worktime = min(max(int(worktime),1),24)
        except:
            normal_init_flag = False
            worktime = '12'
            conf.write(cfg_path, {'worktime': '12'})

        try:
            conf.read(cfg_path)
            secrets = conf.items('secrets')
            proxy = secrets['proxy']
            assert (proxy == 'false') or ('http' in proxy)
            if proxy == 'false':
                proxy = False
            else:
                proxy_a, proxy_b = proxy.split('://')
                while proxy_b[-1] == '/':
                    proxy_b = proxy_b[:-1]
                proxy = {
                    proxy_a: proxy_b
                }
        except:
            self.logger.warning("代理载入错误，不符合http://example.com:port的格式")
            normal_init_flag = False
            proxy = False
            conf.write(cfg_path, {'proxy': 'false'})

        return sessid, csrf_token, buvid, server, mode, userid, loglevel, worktime, proxy, normal_init_flag

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
        api_url = 'https://api.bilibili.com/x/v2/dm/post'
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
            'msg': msg[:80],
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
                # # 因为发现asyncio的post模块似乎用pyinstaller打包会遇到bug，G了

                # async with session.post(api_url, data=payload, headers=headers, cookies=cookies) as resp:
                #     if resp.status == 200:
                #         res = await resp.text()
                #         self.logger.debug(f"步骤3反馈 - {res}")
                #         res = json.loads(res)
                #         if check_success(res):
                #             self.logger.debug(f"步骤3成功 - {bvid}:{cid}:{progress}:{msg} - dmid:{res.get('data',{}).get('dmid','dmid')}")
                #             return True
                #     self.logger.warning(f"步骤3状态码错误 - {resp.status}:{await resp.text()}")
                # await asyncio.sleep(10)
                rsession = requests.session()
                if self.proxy:
                    rsession.proxies = self.proxy
                rsession.mount('https://api.bilibili.com', HTTP20Adapter())
                resp = rsession.post(api_url, data=payload, headers=headers, cookies=cookies)
                if resp.status_code == 200:
                    res = resp.text
                    self.logger.debug(f"步骤3反馈 - {res}")
                    res = json.loads(res)
                    if check_success(res):
                        self.logger.debug(f"步骤3成功 - {bvid}:{cid}:{progress}:{msg} - dmid:{res.get('data',{}).get('dmid','dmid')}")
                        return True
                self.logger.warning(f"步骤3状态码错误 - {resp.status_code}:{resp.text}")
                if self.fail_count >= 3 and resp.status_code != 200:
                    self.global_sleep_daemon.cancel()
                    self.global_sleep_daemon = self.loop.create_task(self.work_work_sleep_sleep(avoid_first_work = True))
                    self.logger.warning(f"多次被拦截触发强制睡眠")
                await asyncio.sleep(10)
            except Exception as e:
                self.logger.warning(f"投送到B站服务器出现错误: {type(e)}:{str(e)}") 
                ...
        else:
            self.logger.debug(f"步骤3失败")
            return False


    async def quest_apply(self, session, query_bvid = None):
        self.logger.debug("步骤1 - 获取")
        if self.working_mode == 'specified':
            assert isinstance(query_bvid, str) # 指定模式下必须输入bvid
        try:
            async with session.get(f'{self.server_url}/api/quest-apply', params={'mode': self.working_mode, 'bvid': str(query_bvid)}) as resp:
                if resp.status == 200:
                    res = json.loads(await resp.text())
                    if res.get('success') == 1:
                        values = res.get('data').values()
                        self.logger.debug(f"步骤1成功 - {values}")
                        return values
                    self.logger.warning(f"步骤1失败 - {res.get('detail')}")
                return False
        except Exception as e:
            self.logger.warning(f"步骤1失败 - exp:{type(e)}:{str(e)}")
            return False

    async def quest_confirm(self, session, bvid, qid, token):
        self.logger.debug("步骤2 - 确认")
        try:
            async with session.get(f'{self.server_url}/api/quest-confirm', params={'bvid': bvid, 'qid': qid, 'token': token}) as resp:
                if resp.status == 200:
                    res = json.loads(await resp.text())
                    if res.get('success') == 1:
                        values = res.get('data').values()
                        self.logger.debug(f"步骤2成功 - {values}")
                        return True
                    self.logger.warning(f"步骤2失败 - {res.get('detail')}")
                return False
        except Exception as e:
            self.logger.warning(f"步骤2失败 - exp:{type(e)}:{str(e)}")
            return False

    async def declare_succeeded(self, session, bvid, qid, token):
        self.logger.debug("步骤5 - 回报")
        try:
            async with session.get(f'{self.server_url}/api/quest-success', params={'bvid': bvid, 'qid': qid, 'token': token, 'wdcr': self.userid}) as resp:
                if resp.status == 200:
                    res = json.loads(await resp.text())
                    if res.get('success') == 1:
                        values = res.get('data').values()
                        self.logger.debug(f"步骤5成功 - {values}")
                        return True
                    self.logger.warning(f"步骤5失败 - {res.get('detail')}")
                return False
        except Exception as e:
            self.logger.warning(f"步骤5失败 - exp:{type(e)}:{str(e)}")
            return False

    async def standard_process(self):

        if self.workflag == False:
            return 1
        try:
            self.logger.info("开始一个新的标准投递流程")
            async with ClientSession() as session:
                res = await self.quest_apply(session, self.query_bvid)
                if res == False:
                    raise TaskFail()
                # else
                qid, progress, cid, bvid, msg, token, bias = res
                self.logger.info(f"【目标 - {bvid}:{cid}:{progress}:{msg}】")
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
                for _, interval in enumerate((10,5,5,10,10,10,10,10,10)):
                    status = await determine_if_cmt_public(session, progress, cid, msg)
                    if status: 
                        self.logger.debug(f"步骤4检查成功")
                        break
                    self.logger.debug(f"步骤4第{_+1}次获取失败")
                    await asyncio.sleep(interval)
                else:
                    raise TaskFailnoSleep()
                res = await self.declare_succeeded(session, bvid, qid, token)
                if not res:
                    raise TaskFail()
                sleep_time = max(0, MIN_INTERVAL - time.time() + start_time)
                self.logger.info(f"投递成功")
                if sleep_time > 0:
                    self.logger.info(f"睡眠等待: {'%.2f' % sleep_time}s")
                await asyncio.sleep(sleep_time)
                return 1
        except TaskFail:
            self.logger.warning(f"投递失败，睡眠")
            await asyncio.sleep(random.randint(10, 20))
            return 2
        except TaskFailnoSleep:
            self.logger.warning(f"投递失败，睡眠")
            return 2
        except TaskAllDone:
            return 3
        return 2

    async def run_daemon(self):

        self.fail_count = 0
        while True:
            if self.close:
                self.logger.info("投递线程终止")
                self.wait_closed.set()
                break

            res = await self.standard_process()
            if res == 3:
                if self.mode == 'specified':
                    self.logger.info(f"接收到全局结束信号")
                    self.close = True; break
                self.logger.info(f"接收到全局结束信号，没有新的弹幕，长睡眠")
                await asyncio.sleep(random.randint(3600, 7200))
            elif res == 2:
                self.fail_count += 1
            elif res == 1:
                self.fail_count = 0
            if self.fail_count >= 5:
                self.logger.warning(f"连续失败5次投递，设置可能出现问题或SESSDATA过期，请检查相关设置，程序退出")
                self.close = True
            await asyncio.sleep(1)

    def pseudo_sigint(self, sig, frame):
        _cur_sigint_time = time.time()
        if (_cur_sigint_time - self._last_sigint_time) < 0.18:
            self.logger.warning("强制终止信号")
            sys.exit(1)
        self._last_sigint_time = _cur_sigint_time
        if not self.close:
            self.logger.info("接收到键盘终止信号，准备退出程序")
            self.logger.info("如果有正在进行的投递流程则会等到本轮投递流程完成")
            self.close = True

    def remote_version(self):
        try:
            text = requests.get('https://dog.464933.xyz/api/latest-client-version').text
            version = json.loads(text)
            assert version['success'] == True
            assert isinstance(version['version'], str)
            assert 5 <= len(version['version']) <= 11
            return version['version'], None
        except Exception as e:
            return None, e

    async def work_work_sleep_sleep(self, avoid_first_work = False):
        while True:
            for _ in range(1):
                if avoid_first_work:
                    avoid_first_work = True
                    break
                self.workflag = True
                self.logger.info("全局计时器：切换为工作状态")
                for _ in range(self.worktime):
                    await asyncio.sleep(3600)
            self.workflag = False 
            self.logger.info(f"全局计时器：切换为休眠状态，将在{self.sleeptime}小时后唤醒")
            for _ in range(self.sleeptime):
                await asyncio.sleep(3600)


    async def run_start(self):
        self.loop = asyncio.get_running_loop()
        self.global_sleep_daemon = self.loop.create_task(self.work_work_sleep_sleep())
        self.loop.create_task(self.run_daemon())
        while not self.wait_closed.is_set():
            await asyncio.sleep(3)
        self.logger.info("程序结束")
        sys.exit(0)


logger.remove()
sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
logger.add('log_debug.txt', level='DEBUG', rotation="5 MB", encoding='utf-8')
worker = Worker(logger)
signal.signal(signal.SIGINT, worker.pseudo_sigint)
asyncio.get_event_loop().run_until_complete(worker.run_start())
input("按回车键或点击右上角叉叉退出")
