from lxml import etree
import re

char_scaner = re.compile('[\u3002\uff1b\uff0c\uff1a\u201c\u201d\uff08\uff09\u3001\uff1f\u300a\u300b\u4E00-\u9FA5\x00-\x7f]+')

async def determine_if_cmt_public(session, target_progress, cid, target_cmt):
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