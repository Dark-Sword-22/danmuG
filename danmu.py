#encoding=utf-8
import re
import os
import sys
import json
import time
import datetime
import asyncio
import danmaku
from math import ceil
from aiohttp.client_exceptions import ClientOSError
from collections import deque
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from loguru import logger
from pipeit import *


VERSION = '0.4.0'
SLEEP_INTERVAL = 5
URL_FORMATTER = "https://cc.163.com/{0}/"


class StreamingSwitch:

    def __init__(self, logger):
        self.logger = logger
        self.status = False
        self.pending_list = deque()

    def is_on(self):
        return self.status

    def on(self):
        self.logger.info("侦测到直播间开启信号，开关打开")
        self.status = True 
        while self.pending_list:
            self.pending_list.popleft().set_result(None)

    def off(self):
        self.logger.info("收到到直播间关闭信号，开关关闭")
        self.status = False

    def hook(self, hanger):
        self.logger.debug(f"添加钩子：{hanger}")
        if self.status:
            hanger.set_result(None)
        else:
            self.pending_list.append(hanger)


class MQueue(asyncio.Queue):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def cls(self):
        await self.put({'msg_type':'Close'})
        while not self.empty():
            await self.get()


class Writer:

    def __init__(self, rid, title, logger):
        '''
        弹幕姬版本: 0.1.0
        直播来源地址: ...
        开始记录时间: 2020-01-01 22:22:22.222
        视频地址: https://bilibili.com/bv..
        时轴修正: +22

        ================================================== * 50
        2021-11-24 00:31:39.333 - 00:12:22.222 - zaima 
        '''
        watch_url = URL_FORMATTER.format(rid)
        title = (
            title
            .replace('/','')
            .replace('\\','')
            .replace('?','')
            .replace(' ','')
            .replace(':','：')
            .replace('*','x')
            .replace('?','？')
            .replace('"','”')
            .replace('|','-')
            .replace('<','《')
            .replace('>','》')
        )
        self._start_time = datetime.datetime.now()
        # UTC-TIME
        self._file_name_time = f"{str(self._start_time + datetime.timedelta(seconds = 3600*8))[:19]}.{str(int(self._start_time.microsecond//1000)).zfill(3)}"
        self.file_name = os.path.join(os.path.abspath('./data/'), f'danmu-{self._file_name_time.replace(":", "-").replace(" ","-").replace(".","-")}-{title}.txt')
        self.logger = logger
        self.last_update_time = time.time()
        with open(self.file_name,'w',encoding='utf-8') as f:
            f.write(f"弹幕姬版本: {VERSION}\n直播来源地址: {watch_url}\n开始记录时间: {self._file_name_time}\n视频地址: \nCID: \n时轴修正: \n\n{'='*50}\n")
        self.logger.info(f"记事本初始化, 弹幕姬版本: {VERSION}")

    def update(self, words: str):
        self.last_update_time = time.time()
        with open(self.file_name,'a',encoding='utf-8') as f:
            current_time = datetime.datetime.now()
            time_diff = (current_time - self._start_time).total_seconds()
            time_diff = self.format_seconds(time_diff)
            f.write(f"{str(current_time + datetime.timedelta(seconds = 3600*8))[:19]}.{str(int(current_time.microsecond // 1000)).zfill(3)} - {time_diff} - {words}\n")

    def format_seconds(self, seconds: int) -> str:
        return f"{str(int(seconds // 3600)).zfill(2)}:{str(int((seconds%3600) // 60)).zfill(2)}:{str(int(seconds%60)).zfill(2)}"


class Observer:

    def __init__(self, rid: str, switch, logger):
        self.loop = asyncio.get_running_loop()
        self.rid = rid
        self.switch = switch
        self.logger = logger
        self.logger.debug("观察员初始化")

    async def detact_if_streaming(self, session):
        room_url = f'https://api.cc.163.com/v1/activitylives/anchor/lives?anchor_ccid={self.rid}'
        channel_id = None
        try:
            async with session.get(room_url) as resp:
                data = json.loads(await resp.text()).get('data')
                if data:
                    channel_id = data.get(self.rid).get('channel_id')
                else:
                    raise Exception('输入错误')

            if channel_id:
                async with session.get(f'https://cc.163.com/live/channel/?channelids={channel_id}') as resp:
                    real_url = json.loads(await resp.text()).get('data')[0].get('sharefile')
                    assert isinstance(real_url, str)
                    return True
            else:
                return False
        except:
            return False

    async def daemon(self):
        fail_count = 0
        fail_target = ceil(60 / SLEEP_INTERVAL)
        while True:
            async with ClientSession() as session:
                for _ in range((24 * 60 * 60) // SLEEP_INTERVAL):
                    loop_st_time = time.time()
                    on_streaming = await self.detact_if_streaming(session)
                    if not on_streaming and _ % 500 == 0:
                        self.logger.info(f"守护线程 - 本次获取到直播间状态为{'开启' if on_streaming else '关闭'}")
                    self.logger.debug(f"守护线程 - 本次获取到直播间状态为{'开启' if on_streaming else '关闭'}")
                    if on_streaming:
                        fail_count = 0
                        self.switch_on()
                    else:
                        fail_count += 1
                        if fail_count >= fail_target:
                            self.switch_off()
                            fail_count = 0
                    sleep_time = max(0, SLEEP_INTERVAL - time.time() + loop_st_time)
                    await asyncio.sleep(sleep_time)

    def switch_on(self):
        if not self.switch.is_on():
            self.switch.on()
    
    def switch_off(self):
        if self.switch.is_on():
            self.switch.off()


class Fisherman:

    def __init__(self, rid, switch, logger):
        self.loop = asyncio.get_running_loop()
        self.logger = logger
        self.switch = switch
        self.rid = rid
        self.q = None
        self.dmc = None
        self._cmt_buffer = deque()
        self._long_cmt_unique_buff = deque() # 重复的长弹幕一般都是刷的
        self._buffer_limit = 100
        self._buffer_count = dict()
        self._buffer_last_refresh_time = time.time()
        self._block_set = {
            '\n',
            '\r',
            '\r\n',
            ',',
            '，',
            '。',
            '.',
            '1',
            '2',
            '3',
            '4',
            '5',
            '7',
            '来了',
            '哈人',
            '欢迎来到直播间',
            '阻碍我的 豆浆烩面！',
            '宝，我能做你的掌中宝嘛~',
            '浑身都充满了阴阳怪气！',
            '阴阳怪气充盈，随时可化身杠精',
            '晦气，晦气啊！',
            '急了 他急了 主播他急了',
            '您的客户端较老，暂不支持显示表情',
            '手气好没办法！',
            '大家快抢，晚了就没了！',
            '恭喜发财！',
            '谁能抢得过我？',
            '下亿把必能赢',
            '得想个办法振他一下',
            '咱仨一起指定嘎嘎乱杀',
            '别急，我去搞2w4救你们',
            '隐族人也不是无敌的，但天海是',
            '冬至冬至，幸福必至~',
        }
        self._biliibli_block_set = ( 
            # 根据弹幕重投失败反馈的B站弹幕拦截关键字
            # 也许与用户等级低有关也说不定
            # 总之可以看得出阿B真的很敏感
            'img',
            'IMG',
            'cc',
            'CC',
            'cnm',
            'CNM',
            'cao',
            'CAO',
            'kale',
            'KALE',
            '艹',
            '狗比',
            '本子',
            '主播',
            '倪哥',
            '想透',
            '紧身衣',
            '工人运动',
            'userCard',
            '一天不振',
            '土豪我们',
            '谢谢老板',
            '小鬼',
            '孝子',
            '贴吧',
            '节奏',
            'fuck',
            'FUCK',
            '法克',
            '双飞',
            '原味',
            'pussy',
            'PUSSY',
            'TMD',
            'tmd',
            '客户端',
            '丑鱼',
            '肥狗',
            '翻墙',
            '拉珠',
            '内斗',
            '[@]',
            '欢迎捧场',
            '欢迎入座',
            '我操',
            '爬爬',
            '叔叔我',
            '冬至冬至',
            '儿子',
            '奇酷比',
            '傀儡妹',
            'DRUG',
            'drug',
            '骚',
            '烧',
            '粪',
            '屎',
            '爬',
            '射',
            '臭',
            '批站',
            '司马脸',
            '蛤蟆',
            '充气娃娃',
            '新姜',
            '鸿儒',
            '烧鸡',
            '牛子',
            '导管',
            '戒色',
            '跳蛋',
            '假证',
            'KALE',
            'kale',
            '卡了',
            '不卡',
            '卡卡',
            '卡死',
            '卡爆',
            '好卡',
            '直肠',
            '开车',
            'hso',
            'HSO',
            '啪啪',
            '哈人',
            '1111',
            '2222',
            '3333',
            '4444',
            '5555',
            '7777',
            '油管',
            '支付宝',
            '烧死',
            '户口本',
            '好色',
            '鬼子',
            '神经病',
            'sjb',
            'SJB',
            '母猪',
            'nmd',
            'NMD',
            '尸体',
            '怪物',
            '爸爸活', 
            '男铜',
            '男同',
            '男桐',
            '男童 ',
            '好死', 
            '口我', 
            '丁丁', 
            '碧池', 
            '普信', 
            '柰子', 
            '奈子', 
            '奶子', 
            '滚出', 
            '牛至', 
            'xbzz', 
            'XBZZ', 
            '哼哼', 
            '啊啊啊啊', 
            '大奶', 
            '阳痿', 
            '开导', 
            '开冲', 
            '浦西',  
            '差不多得了', 
            '晦气', 
            '牛痣', 
            '共济会', 
            '尼格', 
            '尼哥', 
            '栽种', 
            '人上人', 
            '捡尸', 
            '火化',  
            '脚臭',  
            '我焯', 
            '好臭', 
            '收收味', 
            '畜生',  
            '上床', 
            '土狗', 
            '狗屁', 
            'rbq', 
            'RBQ', 
            '肉便器', 
            '撤硕', 
            '那位大人', 
            '炸药', 
            '子弹', 
            '狗洞', 
            '乐色', 
            '吊毛', 
            '司马', 
            '死马', 
            '死妈', 
            '你马', 
            '精神变态', 
            '好似', 
            '好4', 
            '分解', 
            '玩挺大', 
            '人兽',   
            '绅士', 
            '好大', 
            '撒比', 
            '安拉', 
            '阿拉', 
            '肛塞', 
            '社保',
            '挊',
            '龟头',
            '废物',
            '爆菊',
            '胯下',
            '提肛',
            'kkp',
            'KKP',
            '看看p',
            '香草冰',
            '飞机杯',
            '老狗',
            '土狗',
            '64',
            '89',
            '倒模',
            '套套',
            '可不敢',
            '人上人',
            '2B',
            '2b',
            '欧金金',
            '呕',
            '恶臭',
            '萝莉',
            '微博',
            '微信',
            '色图',
            'QQ',
            'qq',
            '二刺猿',
            '炼铜',
            '煉銅',
            '梆硬',
            '恶心',
            'dick',
            'p站',
            'P站',
            '丑死',
            '好丑',
            'Vtuber',
            'vtuber',
            '阿西吧',
            '美爹',
            '野鸡',
            '野猪',
            '神必',
            '死吧',
            '代打',
            '不要停下来',
            '圣母',
            '阴阳',
            '超市',
            '勾把',
            '勾八',
            '小丑',
            'aaa',
            '好紧',
            '好菜',
            '土爆',
            '滚吧',
            '在爬',
            '好腿',
            '腿不错',
            '裸足',
            '命定之死',
            '打手枪',
            '八九',
            '六四',
            '赢麻',
            '寄生',
            '妹控',
            '大湿',
            '仙人板',
            '恐怖要素',
            '拆腻子',
            '割韭菜',
            '點點點',
            '无垢',
            '脏比',
            '修车',
            '五菱',
            '裸女',
            '湿了',
            '爬塔',
            '三上',
            '微软',
            '童车',
            '尾行',
            '坦克',
            '病栋',
            '夜勤',
            '嘿嘿',
            '大肛',
            '🤔',
            '🐮',
            '🙂',
            '乃子',
            '胖次',
            '美兔',
            '冈田',
            '太硬',
            '伪娘',
            '扶她',
            '哥布林',
            '江江',
            '你爹',
            '野爹',
            '中出',
            '贵物',
            '丁真',
            '大大',
            '↑↓',
            '爽死',
            '补魔',
            '黑兽',
            '皮皮虾',
            '腐烂',
            '腐败',
            '玩坏',
            '弹幕',
            '云玩家',
            '王八',
            '恰饭',
            '兄控',
            '嗯了',
            '数一数二',
            'kd',
            'KD',
            '顶不住',
            '老八',
            '屏蔽',
            '孙笑川',
            '小英',
            '偷完',
            '傻子',
            '傻比',
            '智商',
            '佟大为',
            '智障',
        )
        self._re_block_set = (
            re.compile("感谢.*大佬"),
            re.compile("\[emts\][\s\S]*?\[/emts\]"),
            re.compile("\[img\][\s\S]*?\[/img\]"),
            re.compile("<[bu]>.+</[bu]>"),
            re.compile(f"({'|'.join(self._biliibli_block_set)})")
        )
        self._string_filter = lambda x: x.replace('\r\n',' ').replace('\r',' ').replace('\n',' ').strip()

    def ddos_protect(self, cmt):
        '''
        去重逻辑：
            首先热词全部不接受
            然后为每个加入的词建立对应的次数统计，短时间内出现的次数越多，允许的刷新间隔越短。
            即如果词汇零星出现，那么每隔很长一段时间才会写入一次
            如果弹幕风暴大量出现，那么写入间隔会很短。但最短间隔不会低于~0.2s
            另有一时间计数器，被动触发，最短触发间隔60秒，会清空buffer内60s以上的缓存
        '''
        logger.debug(f"{len(self._cmt_buffer)}, {len(self._buffer_count)}")
        if cmt in self._block_set or len(cmt) == 0:
            return None
        for pat in self._re_block_set:
            if pat.search(cmt):
                return None
        current_time = time.time()
        if current_time - self._buffer_last_refresh_time >= 60:
            self._buffer_last_refresh_time = current_time
            for key in tuple(self._buffer_count.keys()):
                _, _time, _ = self._buffer_count[key]
                if (current_time - _time) >= 60:
                    try:
                        del self._buffer_count[key]
                        self._cmt_buffer.remove(key)
                    except:
                        self._buffer_count = {}
                        self._cmt_buffer = deque()
                        return cmt # 正确清理deque后无必要
        #
        if cmt not in self._cmt_buffer:
            self._cmt_buffer.append(cmt)
            self._buffer_count[cmt] = [1, current_time, 2.5]
            while len(self._cmt_buffer) > self._buffer_limit:
                del self._buffer_count[self._cmt_buffer.popleft()]
            return cmt
        else:
            res = None
            _count, _time, _slt = self._buffer_count[cmt]
            self._buffer_count[cmt][0] = _count + 1
            if current_time >= (_time + _slt):
                res = cmt
                self._buffer_count[cmt][1] = current_time
            else:
                self.logger.debug(f"ddos拦截 - {cmt}")
            if _count >= 16:
                nslt = 0.3
            elif _count >= 8:
                nslt = 0.6
            elif _count >= 4:
                nslt = 1.2
            elif _count >= 2:
                nslt = 2
            else:
                nslt = 3
            self._buffer_count[cmt][2] = nslt
            return res

    def ddos_reset(self):
        self._cmt_buffer = deque()
        self._buffer_count = dict()
        self._buffer_last_refresh_time = time.time()

    async def pending(self):
        while True:
            hanger = asyncio.Future()
            self.switch.hook(hanger)
            self.logger.debug("DMC等待开关开启")
            await hanger
            self.logger.info("获取到钩子事件，触发读取进程")
            self.q = MQueue()
            self.dmc = danmaku.DanmakuClient(self.rid, self.q)

            writer_prepared, close_pushed = asyncio.Future(), asyncio.Future()
            self.loop.create_task(self.message_hanlder(writer_prepared, close_pushed))
            self.loop.create_task(self.watch_switch())
            await asyncio.sleep(1)
            await writer_prepared
            try:
                self.logger.debug("DMC进入获取阻塞")
                await self.dmc.start() # block fetching cmts
            except ClientOSError:
                self.logger.debug("DMC触发关闭导致的ssl缓冲溢出") # Normal
            except danmaku.DMCCloseException as e:
                self.logger.debug("DMC触发强制返回异常，跳过__hs.closewait等待时间") # Normal

            await self.q.put({'msg_type':'close'})
            await close_pushed
            self.q.task_done()
            while self._cmt_buffer:
                self._cmt_buffer.pop()
            # 最短间隔
            await asyncio.sleep(5)

    async def watch_switch(self):
        while True:
            await asyncio.sleep(1)
            on_streaming = self.switch.is_on()
            self.logger.debug(f"DMC监视器认为当前直播状态为{on_streaming}")
            if not on_streaming:
                await self.dmc.stop()
                self.logger.debug(f"DMC实例已关闭")
                return 

    async def get_stream_title(self):
        async with ClientSession() as session:
            async with session.get(URL_FORMATTER.format(self.rid)) as resp:
                soup = BeautifulSoup(await resp.text(), 'lxml')
                return soup.find('span', {'class':'js-live-title'}).get('title', '直播间标题获取异常')

    async def git_push(self):
        self.logger.debug("Git push triggered")
        # return 
        def wraper():
            try:
                os.system("git add -A")
                os.system(f'git commit -m "[{str(datetime.datetime.now() + datetime.timedelta(seconds = 8*3600))[:10]}] 弹幕更新"')
                os.system("git push --force")
            except:
                ...
        await self.loop.run_in_executor(None, wraper)
        self.logger.info("Git pushed")

    async def git_pull(self):
        self.logger.debug("Git pull triggered")
        # return
        def wraper():
            try:
                os.system("git checkout .")
                os.system("git fetch --all")
                os.system("git reset --hard origin/main")
                os.system("git pull")
            except:
                ...
        await self.loop.run_in_executor(None, wraper)
        self.logger.info("Git pulled")

    def long_cmt_check(self, cmt):
        if len(cmt) < 13:
            return cmt
        if cmt in self._long_cmt_unique_buff:
            return None
        else:
            self._long_cmt_unique_buff.append(cmt)
            while len(self._long_cmt_unique_buff) > 50:
                self._long_cmt_unique_buff.popleft()
            return cmt

    async def message_hanlder(self, writer_prepared, close_pushed):
        self.logger.info("开辟新的写入线程")
        title, _ = await asyncio.gather(self.get_stream_title(), self.git_pull())
        self.logger.info(f"获取到直播间标题：{title}")
        self.ddos_reset()
        writer = Writer(self.rid, title, self.logger)
        writer_prepared.set_result(None)
        while True:
            m = await self.q.get()
            if m['msg_type'] == 'danmaku':
                cmt = m["content"]
                self.logger.info(f'cmt - {m["name"]}：{m["content"]}')
                cmt = self.long_cmt_check(cmt)
                if cmt:
                    cmt = self.ddos_protect(cmt)
                    if cmt:
                        cmt = self._string_filter(cmt)
                        if ('\n' not in cmt) and (cmt != ''):
                            writer.update(cmt)
            elif m['msg_type'] == 'close':
                self.logger.info("接收到终止信号，写入线程退出")
                self.ddos_reset()
                self._long_cmt_unique_buff = deque()
                await self.git_pull()
                await self.git_push()
                close_pushed.set_result(None)
                return 


async def main(logger):
    watch_id = '361433'
    try:
        with open('watch_id.txt','r',encoding='utf-8') as f:
            watch_id = f.read()
            watch_id = watch_id.strip()
            assert watch_id.isdigit()
    except:
        watch_id = '361433'
    
    logger.info(f"目标网址：{URL_FORMATTER.format(watch_id)}")
    loop = asyncio.get_running_loop()
    # 
    switch = StreamingSwitch(logger)
    observer = Observer(watch_id, switch, logger)
    fisherman = Fisherman(watch_id, switch, logger)
    loop.create_task(fisherman.pending())
    loop.create_task(observer.daemon())

    while True:
        try:
            await asyncio.sleep(3600)
        except KeyboardInterrupt:
            # 用户中断
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                if task._coro.__name__ == "cant_stop_me": continue
                task.cancel()
            await loop.shutdown_default_executor()
            return


# loguru treatments
sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
logger.remove()
# logger.add("log_out.txt", level="DEBUG", rotation="5 MB")
logger.add(sys.stdout, level='INFO')
asyncio.get_event_loop().run_until_complete(main(logger))
