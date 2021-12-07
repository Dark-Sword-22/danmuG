from lxml import etree
from pipeit import *
import re
import os

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