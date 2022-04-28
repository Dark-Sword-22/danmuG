import re 

pat = re.compile('(牛子|\u200b\u200b)')

with open('data/danmu-2022-04-27-20-05-50-585-【Quin】恐惧饥荒.txt', 'r', encoding='utf-8') as f:
    for line in f.readlines():
        print(repr(line), pat.search(line))