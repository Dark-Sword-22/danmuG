import asyncio
import aiofiles
import os
import datetime
import hashlib
import re
from sqlalchemy import Column, Integer, String, DateTime, String, SmallInteger, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, Session, selectinload
from sqlalchemy.engine.url import URL
from sqlalchemy.future import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.schema import UniqueConstraint
from collections import deque
from aiohttp import ClientSession
from lxml import etree
from pipeit import *


Base = declarative_base()


class AbstractTable(Base):
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hash = Column(String(40), unique=True, nullable=False)
    cmt_time = Column(DateTime, nullable=False)
    send_time = Column(Integer, index=True, nullable=False)
    content = Column(String(80), nullable=False)
    bvid = Column(String(20), index=True, nullable=False, default="")
    cid = Column(String(20), index=True, nullable=False, default="")
    status = Column(SmallInteger, index=True, nullable=False, default=0)
    fail_count = Column(SmallInteger, nullable=False, default=0)

'''
状态:
    0 -> 等待发送
    1 -> 客户端确认条目 -> 确认可以发送
    (1.5 -> 客户端已发送)
    2 -> 客户端已确认发送成功
    3 -> 经检查确实发送成功
'''

class BVRelations(Base):
    __tablename__ = 'bv_relations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tname = Column(String(50), unique=True, nullable=False)
    bvid = Column(String(20), unique=True, nullable=False, default="")
    UniqueConstraint('tname', 'bvid', name='uix_1')


def table_for_txt(file_name: str, exists: bool = False):
    if exists:
        return type(file_name, (AbstractTable, ), {'__tablename__': file_name, '__table_args__': {'extend_existing': True}})
    return type(file_name, (AbstractTable, ), {'__tablename__': file_name})

async def scan_and_init(engine):

    def log_parser(string):
        '''
        前置的数据清洗抽象，根据记录格式做出适配
        '''
        logs = string.split('\n')
        return (
            datetime.datetime.strptime(logs[2][logs[2].index(':')+2:], '%Y-%m-%d %H:%M:%S.%f'), 
            'BVzhang',
            ['1', '2', '3', '4', '5'],
            [[3600, 10], [3600, 10], [3600, 10], [3600, 10], [3600, 10]],
            deque(sorted(
                logs[7:] 
                | Filter(lambda x: len(x) >= 37) 
                | Map(
                    lambda x: dict(zip(
                        ('cmt_time', 'content'),  (datetime.datetime.strptime(x[:23], '%Y-%m-%d %H:%M:%S.%f'), x[37:37+80])
                    ))
                )
                | Filter(
                    lambda x: x.setdefault(
                        "hash", 
                        hashlib.sha1(f"{int(x['cmt_time'].timestamp()*1e3)}{x['content']}".encode('utf-8')).hexdigest()
                    )
                    
                ),
                key = lambda x: x['cmt_time'], 
            ))
        )

    def log_parser2(log_time, bvid, cids, prefixs, contents): # input log_parser's output
        try:
            assert len(cids) == len(prefixs)
            for item in prefixs:
                assert isinstance(item, list)
                for _ in item:
                    assert isinstance(_, int)
        except:
            return None, None, False
        res = []
        for item in contents:
            item['send_time'] = int((item['cmt_time'] - log_time).total_seconds() * 1000)
            item['bvid'] = bvid
        for cid, (time_cut, fixer) in zip(cids, prefixs):
            time_cut = time_cut * 1000
            for item in contents:
                item['send_time'] = int(item['send_time'] + fixer * 1000)
                item['cid'] = cid
            while contents and contents[0]['send_time'] <= 0:
                contents.popleft()
            while contents and contents[0]['send_time'] < time_cut:
                res.append(contents.popleft())
            for item in contents:
                item['send_time'] = item['send_time'] - time_cut
        if res: return res, bvid, True
        else: return res, bvid, False

    data_dir = os.path.abspath('../data/')
    for files in os.walk(data_dir):
        files = (
            files[2] 
            | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.txt') 
            | list 
        )
    files.sort(key = lambda x: datetime.datetime.strptime(x[6:6+23], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)
    if len(files) > 22*2: files = files[:22*2]

    tables = [table_for_txt(file_name[:29]) for file_name in files]

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        for file_name, table in zip(files, tables):
            file_path = os.path.join(data_dir, file_name)
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                contents, bvid, _ = log_parser2(*log_parser(await f.read()))
                if not _: continue
            stmt = insert(BVRelations).values({'bvid': bvid, 'tname': file_name[:29]}).on_conflict_do_nothing() # 应加入过期清除机制
            await session.execute(stmt)
                
            stmt = select(table.hash)
            result_hash_set = set((await session.execute(stmt)).scalars().all())
            contents_hash_set = contents | Map(lambda x: x['hash']) | set
            update_set = contents_hash_set.difference(result_hash_set)
            remove_set = result_hash_set.difference(contents_hash_set)

            _step = 1000
            for _ in range(0, len(contents), _step): # orm不到位，自主切不明白
                _tup = contents[_:_+_step] | Filter(lambda x: x['hash'] in update_set) | tuple
                stmt = insert(table).values(_tup).on_conflict_do_nothing() if _tup else text("select 1")
                await session.execute(stmt)
            break
        await session.commit()

async def clean_task_daemon(engine, msg_core):
    while True:
        for _ in range(24*3):
            async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with async_session() as session:
                ...
                # new_core = {}
                # for tab in table:
                #     for line in tab:
                #         if 0< line.status < 3:
                #             stamp = msg_core.get(f'{tname}-{line.id}', None)
                #             if stamp == None:
                #                 line.status = 0
                #                 line.fail_count += 1
                #                 if line.fail_count >= 3:
                #                     line.status = 4
                #                 await session.commit()
                #             elif time.time() - stamp >= 300:
                #                 line.status = 0
                #                 line.fail_count += 1
                #                 if line.fail_count >= 3:
                #                     line.status = 4
                #                 await session.commit()
                #             else:
                #                 new_core[f'{tname}-{line.id}'] = stamp
                # msg_core.clear()
                # msg_core.extend(new_core)
            await asyncio.sleep(random.randint(900, 1500))


class DAL:

    def __init__(self, db_session: Session, msg_core):
        self.session = db_session
        self.table_porj = {}
        self.char_scaner = re.compile('[\u3002\uff1b\uff0c\uff1a\u201c\u201d\uff08\uff09\u3001\uff1f\u300a\u300b\u4E00-\u9FA5\x00-\x7f]+')
        self.msg_core = msg_core
        self.loop = asyncio.get_running_loop()


    async def get_archive_earliest(self, bvid: str):
        table = self.table_porj.get(bvid)
        if not table:
            stmt = select(BVRelations).where(BVRelations.bvid == bvid).order_by(BVRelations.tname.desc()).limit(1)
            item = (await self.session.execute(stmt)).scalars().first()
            if not item:
                # 错误的bvid
                return None
            table = table_for_txt(item.tname, 1)
            self.table_porj[bvid] = table
        stmt = select(table).where(table.status < 4).order_by(table.cmt_time).limit(1)
        item = (await self.session.execute(stmt)).scalars().first()
        if item:
            self.msg_core[f"{tname}-{id}"] = time.time()
            return (item.id, item.send_time, item.cid, item.bvid, item.content)
        return None

    async def client_confirm_quest(self, bvid: str, id: int):
        table = self.table_porj.get(bvid)
        if not table:
            return -2
        stmt = select(table).where(table.id == id)
        item = (await self.session.execute(stmt)).scalars().first()
        if item and item.status == 0:
            item.status = 1
            await self.session.commit()
            return True
        else:
            return -1

    async def client_declare_succeeded(self, bvid: str, id: int, wdcr: str):
        table = self.table_porj.get(bvid)
        if not table:
            return -2
        stmt = select(table).where(table.id == id)
        item = (await self.session.execute(stmt)).scalars().first()
        if item and item.status == 1:
            item.status = 2
            await self.session.commit()
            async with ClientSession() as session:
                for _ in range(3):
                    async with session.get(f"http://comment.bilibili.com/{item.cid}.xml") as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            if len(text) > 1.5e6:
                                return -9
                            if self.determine_if_cmt_exists(item, text):
                                item.status = 3
                                await self.session.commit()
                                return True 
                            else:
                                return -6
                else:
                    item.fail_count = item.fail_count + 1
                    item.status = 0
                    if item.fail_count >= 3:
                        item.status = 4
                    await self.session.commit()
                    return -12
                    

    def determine_if_cmt_exists(self, item: 'itme->table', xml):
        target = self.char_scaner.search(item.content)
        if not target:
            return False
        target = target.group()
        target_time = item.send_time / 1000
        try:
            tree = etree.fromstring(xml.encode('utf-8')).xpath('/i')[0]
            for node in tree:
                if node.tag == 'd':
                    if abs(float(node.get('p').split(',')[0]) - target_time) < 1 and self.char_scaner.search(node.text).group() == target:
                        return True 
            return False
        except:
            raise