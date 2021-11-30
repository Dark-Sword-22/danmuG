import asyncio
import danmaku
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from loguru import logger
import datetime
import time
import os

VERSION = '0.2.0'

class MQueue(asyncio.Queue):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def cls(self):
        await self.put({'msg_type':'Close'})
        while not self.empty():
            await self.get()

class Writer:

    def __init__(self, watch_url, title, logger, activate_interval = 100):
        '''
        弹幕姬版本: 0.1.0
        直播来源地址: ...
        开始记录时间:
        2020-01-01 22:22:22

        ================================================== * 50
        2021-11-24 00:31:39 - 00:12:22 - zaima 
        '''
        title = title.replace('/','').replace('\\','').replace('?','').replace(' ','')
        self._start_time = datetime.datetime.now()
        self._file_name_time = str(self._start_time + datetime.timedelta(seconds = 3600*8))[:19]
        self.file_name = os.path.join(os.path.abspath('./data/'), f'danmu-{self._file_name_time}-{title}.txt'.replace(':', '-').replace(' ','-'))
        self.logger = logger
        self._activate_interval = activate_interval
        self.last_update_time = time.time()
        with open(self.file_name,'w',encoding='utf-8') as f:
            f.write(f"弹幕姬版本: {VERSION}\n直播来源地址: {watch_url}\n开始记录时间:\n{self._file_name_time}\n\n{'='*50}\n")
        self.logger.info(f"记录器初始化成功，直播间标题：{title}")

    def update(self, words: str):
        self.last_update_time = time.time()
        with open(self.file_name,'a',encoding='utf-8') as f:
            current_time = datetime.datetime.now()
            time_diff = (current_time - self._start_time).total_seconds()
            time_diff = self.format_seconds(time_diff)
            f.write(f"{str(current_time + datetime.timedelta(seconds = 3600*8))[:19]} - {time_diff} - {words}\n")

    def format_seconds(self, seconds: int) -> str:
        return f"{str(int(seconds // 3600)).zfill(2)}:{str(int((seconds%3600) // 60)).zfill(2)}:{str(int(seconds%60)).zfill(2)}"

    async def daemon_activate(self, q):
        while True:
            await asyncio.sleep(1)
            current_time = time.time()
            if (current_time - self.last_update_time) >= self._activate_interval:
                self.logger.info("长时间无弹幕，记录器退出。")
                await q.put({"msg_type":"Close"})
                return 

def git_push(logger):
    return
    os.system("git add -A")
    os.system('git commit -m "弹幕更新"')
    os.system("git push")
    logger.debug("Git pushed")
    

def git_pull(logger):
    return 
    os.system("git checkout .")
    os.system("git pull")
    logger.debug("Git pulled")
 

async def get_stream_title(watch_url):
    async with ClientSession() as session:
        async with session.get(watch_url) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, 'lxml')
            return soup.find('span', {'class':'js-live-title'}).get('title')

async def message_hanlder(q, logger, watch_url, dmc):
    _block_set = {
        '欢迎来到直播间',
        '阻碍我的 豆浆烩面！',
        '宝，我能做你的掌中宝嘛~',
        '浑身都充满了阴阳怪气！',
        '阴阳怪气充盈，随时可化身杠精',
        '晦气，晦气啊！',
        '急了 他急了 主播他急了',
    }
    writer = None
    daemon = None
    loop = asyncio.get_running_loop()
    while True:
        m = await q.get()
        if m['msg_type'] == 'Start':
            logger.debug("收到队列开始信号。")
            logger.info("检测到直播间已开播。")
            title, _ = await asyncio.gather(get_stream_title(watch_url), loop.run_in_executor(None, git_pull, logger))
            logger.debug(f"获取到直播间标题：{title}")
            writer = Writer(watch_url, title, logger)
            daemon = loop.create_task(writer.daemon_activate(q))
        elif m['msg_type'] == 'Close':
            logger.info(f"接收队列退出。")
            if writer:
                logger.debug(f"记录器关闭。")
                await loop.run_in_executor(None, git_push, logger)
            if daemon:
                try:
                    daemon.cancel()
                except Exception as e:
                    raise e
                    ...
            await dmc.stop()
            return
        elif m['msg_type'] == 'danmaku':
            cmt = m["content"]
            if writer and cmt not in _block_set:
                logger.info(f'cmt - {m["name"]}：{cmt}')
                writer.update(cmt)

async def main(logger):
    watch_url = 'https://cc.163.com/361433/'
    try:
        with open('watch_url.txt','r',encoding='utf-8') as f:
            watch_url = f.read()
            watch_url = watch_url.strip()
    except:
        watch_url = 'https://cc.163.com/361433/'

    loop = asyncio.get_running_loop()
    q = MQueue()
    SLEEP_INTERVAL = 6

    while True:
        logger.debug("New loop - MAIN")
        dmc = danmaku.DanmakuClient(watch_url, q)
        handler_task = loop.create_task(message_hanlder(q, logger, watch_url, dmc))
        try:
            await dmc.start()
        except KeyboardInterrupt:
            # 用户中断
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                if task._coro.__name__ == "cant_stop_me": continue
                task.cancel()
            await loop.shutdown_default_executor()
            return
        except KeyError:
            # 未开播
            logger.info("检测到直播间未开播")
            await asyncio.sleep(SLEEP_INTERVAL)
        except Exception as e:
            # ...
            raise
        finally:
            await q.cls()

logger.add("log_1.txt", level="DEBUG", rotation="5 MB")
# logger.remove()
# logger.add(sys.stdout, level = 'DEBUG')
asyncio.run(main(logger))