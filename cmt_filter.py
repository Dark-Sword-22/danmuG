import os
import re
import datetime
from pipeit import *

src_dir = os.path.abspath('./data')
for files in os.walk(src_dir):
    files = files[2] | Filter(lambda x: x[:5]=='danmu' and os.path.splitext(x)[1] == '.txt') | list
    break
files.sort(key = lambda x: datetime.datetime.strptime(x[6:6+19], '%Y-%m-%d-%H-%M-%S'), reverse = True)

flt_pats = (
    '\n[0-9-: ]+ - 阻碍我的 豆浆烩面！',
    '\n[0-9-: ]+ - 宝，我能做你的掌中宝嘛~',
) | Map(lambda x: re.compile(x)) | tuple

for file_name in files:
    file_path = os.path.join(src_dir, file_name)
    text = Read(file_path)
    for pat in flt_pats:
        scaned = pat.search(text)
        while scaned:
            text = text[:scaned.start()] + text[scaned.end():]
            scaned = pat.search(text)
    Write(file_path, text)

     #我似冲哥  我似冲哥#  #比如韦天#  #韦天装甲#  #我似韦天#  #韦天动力装甲#  #韦天之诅咒# 