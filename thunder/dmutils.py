from lxml import etree
from pipeit import *
import re
import os
import subprocess
import asyncio
import locale
import codecs
import psutil
from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque
from functools import partial
from ThreadPoolExecutorPlus import ThreadPoolExecutor

char_scaner = re.compile('[\u3002\uff1b\uff0c\uff1a\u201c\u201d\uff08\uff09\u3001\uff1f\u300a\u300b\u4E00-\u9FA5\x00-\x7f]+')

class AsyncIteratorWrapper:

    def __init__(self, obj):
        self._it = iter(obj)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            value = next(self._it)
        except StopIteration:
            raise StopAsyncIteration
        return value

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
        # try:
        #     x2 = x[:x.index('[')]
        # except:
        x2 = ''
        return  (x + x2).strip()

    def items(self, session):
        _session_cont = self.getsession(session)
        _session_cont = _session_cont.split('\n') | Map(lambda x:x.strip()) | Filter(lambda x:x!='') | list
        res = {}
        for _ in _session_cont:
            res[_[:_.index('=')]] = _[_.index('=')+1:]
        return res

async def determine_if_cmt_public(session, target_progress, cid, target_cmt):
    '''
    公屏xml接口判断弹幕是否被他人可见，可见即投稿成功。
    选择轮询方式是因为xml是一个无状态接口，我们认为它引起封号的可能性更小，而且ws的protobuf接口实现更花时间一些，rua。
    '''
    target_cmt = char_scaner.search(target_cmt)
    if not target_cmt:
        return False

    target_cmt = target_cmt.group()
    target_progress /= 1000
    if len(target_cmt) == 0:
        return False 

    try:
        async with session.get(f"http://comment.bilibili.com/{cid}.xml") as resp:
            if resp.status != 200:
                return False 
            else:
                xml = await resp.text()
                try:
                    tree = etree.fromstring(xml.encode('utf-8'), etree.XMLParser(resolve_entities=False)).xpath('/i')[0]
                    for node in tree:
                        if node.tag == 'd':
                            if abs(float(node.get('p').split(',')[0]) - target_progress) < 1 and char_scaner.search(node.text).group() == target_cmt:
                                return True 
                    return False
                except:
                    return False
    except:
        return False


async def git_pull(loop):
    # return
    def wraper():
        try:
            os.system("git checkout .")
            os.system("git fetch --all")
            os.system("git reset --hard origin/main")
            os.system("git pull")
        except:
            ...
    await loop.run_in_executor(None, wraper)


class SelectorManager:

    def __init__(self, proc):
        self.proc = proc
        self.fileobj = proc.stdout
        self._selector = DefaultSelector()

    def __enter__(self):
        self._selector.register(self.fileobj, EVENT_READ, None)
        return self._selector

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._selector.unregister(self.fileobj)
        self._selector.close()
        self._kill_proc()

    def _kill_proc(self):
        ps_proc = psutil.Process(self.proc.pid)
        for ps_proc_c in ps_proc.children(recursive=True):
            ps_proc_c.kill()
        ps_proc.kill()

class EpolledTailFile:

    pool = ThreadPoolExecutor()

    def __init__(self, file_name, encoding=None, n=50):
        self.file_name = file_name
        self.encoidng = encoding
        self.n = n
        if encoding == None:
            self.encoding = codecs.lookup(locale.getpreferredencoding()).name
        self.ready_lines = deque()
        self.read_wait = None
        self._close = False

    def _listener_daemon(self):
        proc = subprocess.Popen(
            # f'ping {self.file_name}', 
            f'tail -f {self.file_name}', 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            shell=True,
            close_fds=True,
        )
        os.set_blocking(proc.stdout.fileno(), False)
        with SelectorManager(proc) as selector:
            while True:
                if self._close: break
                events = selector.select(timeout=10)
                for key, _ in events:
                    self.loop.call_soon_threadsafe(partial(self.addline, proc.stdout))

    def addline(self, fileobj):
        buf = bytearray()
        while True:
            rd = fileobj.readline()
            if len(rd) == 0:
                break
            buf += rd
        if len(buf) > 0:
            self.ready_lines.append(buf)
            if self.read_wait and not self.read_wait.is_set():
                self.read_wait.set()

    async def upstream(self):
        loop = asyncio.get_running_loop()
        while True:
            if self.ready_lines:
                self.read_wait = None
                res = bytearray()
                while self.ready_lines:
                    res += self.ready_lines.popleft()
                return res.decode(self.encoding, errors='replace')
            self.read_wait = asyncio.Event()
            await self.read_wait.wait()

    def start_listen(self):
        self.loop = asyncio.get_running_loop()
        self.loop.run_in_executor(self.__class__.pool, self._listener_daemon)

    def close(self):
        self._close = True
