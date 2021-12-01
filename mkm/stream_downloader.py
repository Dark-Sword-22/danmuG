import asyncio
import aiohttp
import ujson as json
from pipeit import *
from collections import deque
import re
import time
import datetime
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stdout, level = 'DEBUG')

class NotExistsError(Exception):
    ...

class Container:

    def __init__(self):
        self.container = deque()
        self.wait_list = deque()
        self._cmax = 20
        self.loop = asyncio.get_running_loop()
        self.path = os.path.abspath('.')
        self.loop.create_task(self.download_daemon())

    def unitag(self, string):
        return string[:string.index('.ts')+3]

    def update(self, queue: list, real_url: str):
        prefix = real_url[:max(len(real_url) - real_url[::-1].index('/'),1)]
        queue = [(self.unitag(_), _) for _ in queue]
        for tag, cont in queue:
            if tag not in self.container | Map(lambda x:x[0]):
                self.container.append((tag, cont))
                logger.info(f"New stream part found: {tag}")
                self.wait_list.append((f"{prefix}{cont}", f"{str(datetime.datetime.now())[:19].replace(':','-').replace(' ','-')}.ts"))
                while len(self.container) >= self._cmax:
                    self.container.popleft()

    async def download_daemon(self):
        async with aiohttp.ClientSession() as session:
            while True:
                await asyncio.sleep(0.1)
                if len(self.wait_list) > 0:
                    download_url, file_name = self.wait_list.popleft()
                    self.loop.create_task(self.download_single_file(session, download_url, file_name))

    async def download_single_file(self, session, url, file_name):
        logger.info(f"Downloading file: {file_name}, from: {url[-64:]}")
        async with session.get(url) as response:
            with open(os.path.join(self.path, file_name), 'wb') as f:
                async for data in response.content.iter_chunked(1024 * 256):
                    f.write(data)

class CC:

    def __init__(self, rid, session):
        self.rid = rid
        self.session = session
        self._pat = re.compile('#EXTINF:[0-9\.]+?,\n.+?\n')

    async def get_real_url(self):
        room_url = f'https://api.cc.163.com/v1/activitylives/anchor/lives?anchor_ccid={self.rid}'
        channel_id = None
        async with self.session.get(room_url) as resp:
            data = json.loads(await resp.text()).get('data', 0)
            if data:
                channel_id = data.get(self.rid).get('channel_id', 0)
            else:
                logger.error("输入错误")
                raise Exception('输入错误')
        
        if channel_id:
            async with self.session.get(f'https://cc.163.com/live/channel/?channelids={channel_id}') as resp:
                real_url = json.loads(await resp.text()).get('data')[0].get('sharefile')
                return real_url
        else:
            logger.info("直播间不存在")
            raise NotExistsError('直播间不存在')

    async def get_m3u8_content(self, real_url):
        async with self.session.get(real_url) as resp:
            return await resp.text()

    def m3u8_spliter(self, content):
        return self._pat.findall(content) | Map(lambda x: x.split('\n')[-2]) | list

async def main():
    main_refresh_interval = 1.5
    while True:
        watch_id = '361433'
        try:
            with open('watch_id.txt','r',encoding='utf-8') as f:
                watch_id = f.read()
                watch_id = watch_id.strip()
        except:
            watch_id = '361433'
        logger.info(f"重新开始获取循环, 监视ID: {watch_id}")
        async with aiohttp.ClientSession() as session:
            container = Container()
            while True:
                try:
                    st_time = time.time()
                    cc_client = CC(watch_id, session)
                    real_url = await cc_client.get_real_url()
                    ts_list = cc_client.m3u8_spliter(await cc_client.get_m3u8_content(real_url))
                    container.update(ts_list, real_url)
                    sleep_time = max(0, main_refresh_interval - time.time() + st_time)
                    await asyncio.sleep(sleep_time)
                except NotExistsError:
                    await asyncio.sleep(2)
                    break

asyncio.get_event_loop().run_until_complete(main())