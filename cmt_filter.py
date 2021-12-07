import os
import re
import datetime
from pipeit import *

src_dir = os.path.abspath('./data')
for files in os.walk(src_dir):
    files = files[2] | Filter(lambda x: x[:5]=='danmu' and os.path.splitext(x)[1] == '.txt') | list
    break
files.sort(key = lambda x: datetime.datetime.strptime(x[6:6+23], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)
files = files[:100]

flt_pats = (
    '\n[0-9-: \.]+ - [0-9-: \.]+ - \.',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 1',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 2',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 3',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 阻碍我的 豆浆烩面！',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 宝，我能做你的掌中宝嘛~',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 阻碍我的 豆浆烩面！',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 宝，我能做你的掌中宝嘛~',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 浑身都充满了阴阳怪气！',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 阴阳怪气充盈，随时可化身杠精',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 晦气，晦气啊！',
    '\n[0-9-: \.]+ - [0-9-: \.]+ - 急了 他急了 主播他急了',
) | Map(lambda x: re.compile(x)) | tuple

key_word_pats = (
    re.compile('(cc|CC|cnm|CNM|cao|CAO|kale|KALE|艹|狗比|拉屎|本子|主播)'),
)

for file_name in files:
    file_path = os.path.join(src_dir, file_name)
    text = Read(file_path)
    for pat in flt_pats:
        scaned = pat.search(text)
        while scaned:
            text = text[:scaned.start()] + text[scaned.end():]
            scaned = pat.search(text)
    # 
    text = text.split('\n')
    text_new = text[:8] | Map(lambda x:x + '\n') | list
    for line in text[8:]:
        for pat in key_word_pats:
            if pat.search(line):
                break
        else:
            text_new.append(line + '\n')
    while text_new[-1] == '\n': 
        text_new.pop()
    text_new = ''.join(text_new)
    Write(file_path, text_new)