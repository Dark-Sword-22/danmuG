from pipeit import *
import re
import datetime

file_name = 'danmu-2022-02-27-19-47-46-553-【Quin】艾尔登法环XBOX版.txt'
with open(file_name,'r',encoding='utf-8') as f:
    a = f.readlines()

def format_seconds(seconds: int) -> str:
    return f"{str(int(seconds // 3600)).zfill(2)}:{str(int((seconds%3600) // 60)).zfill(2)}:{str(int(seconds%60)).zfill(2)}"

sttime = datetime.datetime.strptime(re.search('[\d]{4}-[\d]{2}-[\d]{2} [\d]{2}:[\d]{2}:[\d]{2}\.[\d]{3}', head[2]).group(), '%Y-%m-%d %H:%M:%S.%f')
out = []
head, cont = a[:8] , a[8:]
for l in cont:
    a = re.search('[\d]{4}-[\d]{2}-[\d]{2} [\d]{2}:[\d]{2}:[\d]{2}\.[\d]{3}', l).group()
    b = re.search(' - [\d]{2}:[\d]{2}:[\d]{2} - ', l).group()
    time1 = datetime.datetime.strptime(a, '%Y-%m-%d %H:%M:%S.%f')
    timediff = (time1 - sttime).total_seconds()
    ll = l.replace(b, f" - {format_seconds(timediff)} - ")
    out.append(ll)

bb = head + out
with open(file_name,'w',encoding='utf-8') as f:
    f.writelines(bb)