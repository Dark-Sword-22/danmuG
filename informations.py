import os
import datetime
import asyncio
import json
from aiohttp import ClientSession
from pipeit import *

async def main():
    api_url = 'https://api.bilibili.com/x/player/pagelist'
    src_dir = os.path.abspath('./data')
    for src_files in os.walk(src_dir):
        src_files = src_files[2] | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.txt') | list
        break
    src_files.sort(key = lambda x: datetime.datetime.strptime(x[6:6+23], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)
    src_files = src_files[:100]

    _get = lambda x: x[x.index(':')+1:].strip()
    for file_name in src_files:
        file_path = os.path.join(src_dir, file_name)
        content = Read(file_path).split('\n')
        bvid = _get(content[3])
        cids = _get(content[4])
        if len(bvid) > 5 and cids == '':
            bvid = bvid[len(bvid) - bvid[::-1].index('/'):]
            await asyncio.sleep(1)
            async with ClientSession() as session:
                async with session.get(api_url, params={'bvid': bvid, 'jsonp': 'jsonp'}) as resp:
                    try:
                        assert resp.status == 200
                        res = json.loads(await resp.text())
                        assert res.get("code") == 0
                        assert isinstance(res.get("data"), list)
                    except:
                        continue

            cids = res['data'] | Map(lambda x: x['cid']) | list
            durations = res['data'] | Map(lambda x: [x['duration'], 0]) | list
            content[4] = f"CID: {json.dumps(cids)}"
            content[5] = f"时轴修正: {json.dumps(durations)}"

            Write(file_path, '\n'.join(content) + '\n')



asyncio.get_event_loop().run_until_complete(main())