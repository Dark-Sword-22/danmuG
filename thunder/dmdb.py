import asyncio
import aiofiles
import os
import datetime
import hashlib
import re
import random
import time
import json
from sqlalchemy import Column, Integer, String, DateTime, String, SmallInteger, text, Boolean
from sqlalchemy import delete, select, update, inspect, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, Session, selectinload
from sqlalchemy.engine.url import URL
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.schema import UniqueConstraint
from collections import deque
from aiohttp import ClientSession
from lxml import etree
from dmutils import char_scaner, determine_if_cmt_public
from hmac import compare_digest
from pipeit import *

class BaseModel:

    @classmethod
    def get_model_by_table_name(cls, table_name):
        registry_instance = getattr(cls, "registry")
        for mapper_ in registry_instance.mappers:
            model = mapper_.class_
            model_class_name = model.__tablename__
            if model_class_name == table_name:
                return model


Base = declarative_base(cls=BaseModel)
GlobLock = asyncio.Lock()
_MAXRETRY = 1

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
    rnd = Column(Integer, nullable=False, default=0)

'''
状态:
    0 -> 等待发送
    1 -> 客户端确认条目 -> 确认可以发送
    (1.5 -> 客户端已发送)
    2 -> 客户端已确认发送成功 （由于这个状态存在时间太短，立即就能验证，目前被废弃，直接1到3）
    3 -> 经检查确实发送成功
'''

class BVRelations(Base):
    __tablename__ = 'bv_relations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tname = Column(String(50), unique=True, nullable=False)
    bvid = Column(String(20), unique=True, nullable=False, default="")
    UniqueConstraint('tname', 'bvid', name='uix_1')

class BVStatus(Base):
    __tablename__ = 'bv_status'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bvid = Column(String(20), unique=True, nullable=False, default="")
    create_time = Column(DateTime, nullable=False)
    finished = Column(Boolean, nullable=False, default=False)

class Contributors(Base):
    __tablename__ = 'contributors'

    uid = Column(Integer, primary_key=True, autoincrement=True)
    uname = Column(String(16), unique=True, nullable=False, default="")
    last_update_time = Column(DateTime, nullable=False)
    total_count = Column(Integer, index=True, nullable=False, default=1)
    total_chars = Column(Integer, nullable=False, default=1)

async def scan_and_reload(engine):

    def _get(x):
        if ":" in x:
            return x[x.index(':')+1:].strip()
        else:
            return ""

    def valid_check(cids, prefixs, bvid):
        try:
            assert len(cids) == len(prefixs)
            for item in prefixs:
                assert isinstance(item, list)
                for _ in item:
                    assert isinstance(_, int)
            assert len(bvid) > 0
            assert len(cids) > 0
            assert len(prefixs) > 0
            return True
        except:
            return False

    def load_basic_status(list_of_strings):
        bvid = _get(list_of_strings[3])
        if len(bvid) > 5: bvid = bvid[len(bvid) - bvid[::-1].index('/'):]
        else: bvid = ''
        cids = _get(list_of_strings[4])
        if len(cids) > 5: cids = json.loads(cids) | Map(lambda x: str(x)) | list
        else: cids = []
        prefixs = _get(list_of_strings[5])
        if len(prefixs) > 5: prefixs = json.loads(prefixs)
        else: prefixs = []
        return bvid, cids, prefixs

    def log_parser(string):
        '''
        前置的数据清洗抽象，根据记录格式做出适配
        '''
        logs = string.split('\n')
        bvid, cids, prefixs = load_basic_status(logs)
        res = (
            datetime.datetime.strptime(logs[2][logs[2].index(':')+2:], '%Y-%m-%d %H:%M:%S.%f'), 
            bvid,
            cids,
            prefixs,
            deque(sorted(
                logs[8:] 
                | Filter(lambda x: len(x) >= 37) 
                | Map(
                    lambda x: dict(zip(
                        ('cmt_time', 'content'),  (datetime.datetime.strptime(x[:23], '%Y-%m-%d %H:%M:%S.%f'), x[37:37+80])
                    ))
                ),
                key = lambda x: x['cmt_time'], 
            ))
        )
        for item in res[4]:
            item["hash"] = hashlib.sha1(f"{int(item['cmt_time'].timestamp()*1e3)}{item['content']}".encode('utf-8')).hexdigest()
        return res

    def log_parser2(create_time, bvid, cids, prefixs, contents): # input log_parser's output
        if not valid_check(cids, prefixs, bvid):
            return None, None, None, False
        res = []
        for item in contents:
            item['send_time'] = int((item['cmt_time'] - create_time).total_seconds() * 1000)
            item['bvid'] = bvid
            item['rnd'] = random.randint(0,1e6)
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
        if res: return res, bvid, create_time, True
        else: return res, bvid, create_time, False

    data_dir = os.path.abspath('../data/')
    for files in os.walk(data_dir):
        files = (
            files[2] 
            | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.txt') 
            | list 
        )
    files.sort(key = lambda x: datetime.datetime.strptime(x[6:6+23], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)
    if len(files) > 22: files = files[:22]

    files_legal = []
    for file_name in files:
        file_path = os.path.join(data_dir, file_name)
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            contents, bvid, create_time, _ = log_parser2(*log_parser(await f.read()))
            if not _: continue
            files_legal.append(file_name)

    tables = [
        Base.get_model_by_table_name(file_name) if Base.get_model_by_table_name(file_name) else \
        type(file_name, (AbstractTable, ), {'__tablename__': file_name}) \
        for file_name in files_legal | Map(lambda x:x[:29])
    ]

    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    for file_name, table in zip(files_legal, tables):
        async with GlobLock:
            async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with async_session() as session:
                file_path = os.path.join(data_dir, file_name)
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    contents, bvid, create_time, _ = log_parser2(*log_parser(await f.read()))
                    if not _: continue

                stmt = insert(BVStatus).values({'bvid': bvid, 'create_time': create_time}).on_conflict_do_update(index_elements=['bvid'], set_={'create_time': create_time})
                await session.execute(stmt)
                stmt = insert(BVRelations).values({'bvid': bvid, 'tname': file_name[:29]}).on_conflict_do_nothing()
                await session.execute(stmt)

                stmt = select(table.hash)
                table_content = (await session.execute(select(table))).scalars().all()
                result_hash_set = table_content | Map(lambda x: f"{x.hash}-{x.cid}-{x.send_time}") | set 
                contents_hash_set = contents | Map(lambda x: x.setdefault('unique', f"{x['hash']}-{x['cid']}-{x['send_time']}")) | set
                update_set = contents_hash_set.difference(result_hash_set)
                remove_set = result_hash_set.difference(contents_hash_set)
                _step = 1000

                # Remove
                remove_items = table_content | Filter(lambda x: f"{x.hash}-{x.cid}-{x.send_time}" in remove_set)
                for _ in range(0, len(table_content), _step):
                    remove_ids = [x.id for _, x in zip(range(_step), remove_items)]
                    if remove_ids:
                        stmt = delete(table).where(table.id.in_(remove_ids))
                        await session.execute(stmt)
                # Insert
                for _ in range(0, len(contents), _step): # orm不到位，自主切不明白
                    _wrap = lambda x, y: y
                    _tup = contents[_:_+_step] | Filter(lambda x: x['unique'] in update_set) | Map(lambda x: _wrap(x.pop('unique'),x)) | tuple
                    if _tup:
                        stmt = insert(table).values(_tup).on_conflict_do_nothing() if _tup else text("select 1")
                        await session.execute(stmt)  
                await session.commit()

async def clean_task_daemon(engine, msg_core):
    while True:
        async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
        async with async_session() as session:
            stmt = select(BVRelations.tname).where(BVRelations.bvid==BVStatus.bvid).where(BVStatus.finished==False).order_by(BVStatus.create_time.desc()).limit(23)
            table_names_to_check = set((await session.execute(stmt)).scalars().all())
            table_to_check = AbstractTable.__subclasses__() | Filter(lambda x: x.__tablename__ in table_names_to_check) | list
        for table in table_to_check:
            async with GlobLock:
                async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
                async with async_session() as session:
                    # 检查表是否全部投递完毕
                    hit = (await session.execute(select(table).where(table.status < 3).limit(1))).scalars().all()
                    if not hit:
                        stmt = update(BVStatus).where(BVStatus.bvid == select(BVRelations.bvid).where(BVRelations.tname == table.__tablename__).limit(1)).values(finished = True)
                        await session.execute(stmt, execution_options={"synchronize_session": 'fetch'})
                        await session.commit()
                        # 全部投递完毕则更新并跳过
                        continue
                    # 检查并标记单P过量弹幕
                    count_lines = (await session.execute(select(table.cid, func.count(table.id)).where(table.status==0).group_by(table.cid))).all()
                    for cid, cid_count in count_lines:
                        diff_num = cid_count - 4800
                        if diff_num > 0:
                            devalues = (await session.execute(select(table).where(table.status==0).where(func.length(table.content) <= 7).order_by(func.random()).limit(diff_num))).scalars().all()
                            for item in devalues:
                                item.fail_count = 4
                                item.status = 3
                    # 更新表中未处理的连续失败状态，理论上这部分应该在业务中被完成，但可能由于各种原因遗漏。
                    latest_update = (await session.execute(select(table.id).where(table.status >= 3).where(table.fail_count<4).order_by(table.cmt_time.desc()).limit(1))).scalars().first()
                    if latest_update:
                        total_line_count = (await session.execute(select(func.count(table.id)))).scalars().first()
                        if (total_line_count - latest_update) < 500:
                            stmt = select(table).where(table.id == 1)
                        else:
                            stmt = select(table).where(table.id == 1).where(table.id < max(0, latest_update - 500))
                        archives = (await session.execute(stmt)).scalars().all()
                        if archives:
                            for item in archives:
                                item.fail_count += 1
                                if item.fail_count >= _MAXRETRY:
                                    item.status = 4
                                else:
                                    item.status = 0
                    await session.commit()
        await asyncio.sleep(random.randint(900, 1500))

async def task_status_daemon(engine, table, qid):
    await asyncio.sleep(180)
    async_session = sessionmaker(engine, expire_on_commit=True, class_=AsyncSession)
    async with async_session() as session:
        item = (await session.execute(select(table).where(table.id == qid))).scalars().first()
        if item:
            if item.status < 3:
                item.fail_count += 1
                if item.fail_count >= _MAXRETRY:
                    item.status = 4
                else:
                    item.status = 0
        # table finished?
        unfinished_items = (await session.execute(select(table).where(table.status < 3).limit(1))).scalars().all()
        if not unfinished_items:
            stmt = update(BVStatus).where(BVStatus.bvid == select(BVRelations.bvid).where(BVRelations.tname == table.__tablename__)).values(finished = True)
        await session.commit()

class DAL:

    _table_proj = {}

    def __init__(self, db_engine, db_session: Session, msg_core):
        self.engine = db_engine
        self.session = db_session
        self.table_porj = self.__class__._table_proj
        self.msg_core = msg_core
        self.create_token = lambda x: hashlib.sha1(x.encode('utf-8')).hexdigest()[:8]
        self.loop = asyncio.get_running_loop()


    async def get_archive_earliest(self, mode: str, bvid: str):
        if mode == 'specified':
            table = self.table_porj.get(bvid)
            if bvid=='None':
                return -4
            if not table:
                stmt = select(BVRelations).where(BVRelations.bvid == bvid).order_by(BVRelations.tname.desc()).limit(1)
                rlitem = (await self.session.execute(stmt)).scalars().first()
                if not rlitem:
                    # 错误的bvid
                    return -4
                table = Base.get_model_by_table_name(rlitem.tname)
                if table == None:
                    return -4
                self.table_porj[bvid] = table
        else:
            # mode = 'auto'
            stmt = select(BVRelations).filter(BVStatus.finished==False).filter(BVStatus.bvid==BVRelations.bvid).order_by(BVStatus.create_time.desc()).limit(1)
            rlitem = (await self.session.execute(stmt)).scalars().first()
            if rlitem == None:
                # 所有工作均已完成
                return True
            table = Base.get_model_by_table_name(rlitem.tname)
            if table == None:
                return -4
            bvid = rlitem.bvid
            self.table_porj[bvid] = table

        stmt = select(table).where(table.status == 0).order_by(table.cmt_time).limit(23)
        item_set = (await self.session.execute(stmt)).scalars().all()
        if item_set:
            item = random.sample(item_set, 1)[0]
            return (
                item.id, 
                item.send_time, 
                item.cid, 
                item.bvid, 
                item.content, 
                self.create_token(f"{item.send_time}-{item.rnd}"),
                1 # 补位为0表示无任务
            ) 
        else:
            stmt = select(table).where(table.status == 1).order_by(table.cmt_time).limit(88)
            item_set = (await self.session.execute(stmt)).scalars().all()
            if len(item_set) > 10:
                item = random.sample(item_set, 1)[0]
                item.fail_count += 1
                if item.fail_count >= _MAXRETRY:
                    item.status = 4
                else:
                    item.status = 0
            else:
                # 确实没有任务了
                for item in item_set:
                    item.status = 4
                    item.fail_count = _MAXRETRY
                await self.session.execute(update(BVStatus).where(BVStatus.bvid == bvid).values(finished=True))
            await self.session.commit()
            return True

    async def client_confirm_quest(self, bvid: str, qid: int, token: str):
        table = self.table_porj.get(bvid)
        if not table:
            return -2
        stmt = select(table).where(table.id == qid)
        item = (await self.session.execute(stmt)).scalars().first()
        if item and item.status == 0:
            if compare_digest(self.create_token(f"{item.send_time}-{item.rnd}"), token):
                item.status = 1
                await self.session.commit()
                self.loop.create_task(task_status_daemon(self.engine, table, qid))
                return True
            else:
                return -3
        else:
            return -1

    async def client_declare_succeeded(self, bvid: str, qid: int, token: str, wdcr: str):
        table = self.table_porj.get(bvid)
        if not table:
            return -2
        stmt = select(table).where(table.id == qid)
        item = (await self.session.execute(stmt)).scalars().first()
        if item and item.status == 1:
            if not compare_digest(self.create_token(f"{item.send_time}-{item.rnd}"), token):
                return -3
            else:
                async with ClientSession() as http_session:
                    '''
                    目前实际使用中出现约0.8%概率的客户端发送成功，服务器端获取不到的情况。会导致弹幕刷双份，体验一般。
                    不知道产生原因，可能是cdn刷新导致，挂上更新延迟也没用。干脆停了看看效果吧
                    '''
                    # for _ in range(3):
                    #     res = await determine_if_cmt_public(http_session, item.send_time, item.cid, item.content)
                    #     if res:break
                    #     if _ < 2: await asyncio.sleep(3)
                    # else:
                    #     res = False
                    res = True
                    if res:
                        item.status = 3
                        # table finish?
                        table_finish = await self.check_finished(table)
                        if table_finish:
                            stmt = update(BVStatus).where(BVStatus.bvid == bvid).values(finished=True)
                            await self.session.execute(stmt)
                        stmt = select(Contributors).where(Contributors.uname == wdcr).limit(1)
                        person = (await self.session.execute(stmt)).scalars().first()
                        _ctime = datetime.datetime.now() + datetime.timedelta(seconds=3600)
                        if person:
                            person.total_count += 1
                            person.total_chars += len(item.content)
                            person.last_update_time = _ctime
                            await self.session.commit()
                        else:
                            self.session.add(Contributors(uname=wdcr, last_update_time=_ctime))
                            await self.session.commit()
                        return True
                    else:
                        item.fail_count = item.fail_count + 1
                        item.status = 0
                        if item.fail_count >= _MAXRETRY:
                            item.status = 4
                        table_finish = await self.check_finished(table)
                        if table_finish:
                            stmt = update(BVStatus).where(BVStatus.bvid == bvid).values(finished=True)
                            await self.session.execute(stmt)
                        await self.session.commit()
                        return -5
        else:
            return -1

    async def check_finished(self, table):

        stmt = select(table).where(table.status < 3).limit(1)
        unfinished_items = (await self.session.execute(stmt)).scalars().all()
        if not unfinished_items:
            return True
        else:
            return False

    async def fetch_superman(self):
        res = await self.session.execute(select(Contributors).order_by(Contributors.total_count.desc()).limit(50))
        res = res.scalars().all()
        return res | Map(lambda x: {"name": x.uname, "datetime": str(x.last_update_time + datetime.timedelta(seconds = 8*3600))[:19], "wordcount": x.total_chars}) | list

    async def fetch_accomplishment_rate(self):

        def use_inspector(conn):
            inspector = inspect(conn)
            return inspector.get_table_names()

        async with self.engine.connect() as conn:
            tables = await conn.run_sync(use_inspector)
        
        tables = tables | Filter(lambda x: x[:6] == 'danmu-' and x[6:10].isdigit()) | list 
        tables.sort(key = lambda x: datetime.datetime.strptime(x[6:6+21], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)
        tables = tables[:20]

        res = {}
        for table_name in tables:
            model = Base.get_model_by_table_name(table_name)
            if model:
                stmt = select(func.count()).select_from(select(model).where(model.status>=3))
                r = (await self.session.execute(stmt)).scalars().first()
                if r:
                    res[table_name] = r
        return res
