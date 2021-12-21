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

_biliibli_block_set = ( 
    # 根据弹幕重投失败反馈的B站弹幕拦截关键字
    # 也许与用户等级低有关也说不定
    # 总之可以看得出阿B真的很敏感
    '豆浆烩面！',
    '掌中宝嘛~',
    '充满了阴阳怪气',
    '阴阳怪气充盈',
    '一天不振',
    '晦气，晦气啊',
    '指定嘎嘎乱杀',
    '我去搞2w4救你们',
    '隐族人也不是无敌的',
    '冬至冬至',
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
    '拉.{0,1}屎',
    '本子',
    '主播',
    '好烧',
    '骚',
    '倪哥',
    '尼哥',
    '想透',
    '紧身衣',
    '工人运动',
    'userCard',
    '土豪我们',
    '谢谢老板',
    '小鬼',
    '孝子',
    '贴吧',
    '节奏',
    'fuck',
    'FUCK',
    '法克'
)


key_word_pats = (
    re.compile(f'({"|".join(_biliibli_block_set)})'),
)

for file_name in files:
    file_path = os.path.join(src_dir, file_name)
    text = Read(file_path)

    text = text.split('\n')
    text_new = text[:8] | Map(lambda x:x + '\n') | list
    for line in text[8:]:
        for pat in key_word_pats:
            if len(line) == 38 and line[-1] in ['.','1','2','3']:
                break
            if pat.search(line):
                break
        else:
            text_new.append(line + '\n')
    while text_new[-1] == '\n': 
        text_new.pop()
    text_new = ''.join(text_new)
    Write(file_path, text_new)