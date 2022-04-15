# 需要在主目录下执行
# https://gist.github.com/GoodManWEN/f4c84cc3ba617697eade59733ab6c4ed
import os
import re
import time
import subprocess
from win32file import CreateFile, SetFileTime, GetFileTime, CloseHandle
from win32file import GENERIC_READ, GENERIC_WRITE, OPEN_EXISTING
from pywintypes import Time # pip install pywin32
from pipeit import *

# config for chinese
out = os.popen('git config --global --list').read()
conf = re.search('core.quotepath=(true|false)\n', out)
quotepath_conf = True
if conf:
    if 'false' in conf.group():
        quotepath_conf = False
os.popen('git config --global core.quotepath false')

#
def modifyFileTime(filePath, targetTime):
    try:
        cTime_t, mTime_t, aTime_t = targetTime, targetTime, targetTime

        fh = CreateFile(filePath, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, 0)
        createTimes, accessTimes, modifyTimes = GetFileTime(fh)
 
        createTimes = Time(time.mktime(cTime_t))
        accessTimes = Time(time.mktime(aTime_t))
        modifyTimes = Time(time.mktime(mTime_t))
        SetFileTime(fh, createTimes, accessTimes, modifyTimes)
        CloseHandle(fh)
        return 0
    except:
        return 1

# 
root = os.getcwd()
pfiles = subprocess.Popen('git ls-tree -r --name-only HEAD', shell=False, stdout = subprocess.PIPE)
msg_raw = ''
for line in pfiles.stdout:
    msg_raw += line.decode(encoding='utf-8', errors="ignore")
files = msg_raw.split('\n') | Filter(lambda x: len(x) > 0 and x[0] != '.') | Map(lambda x: x[:-1] if x[-1] == '\n' else x) | list 
for idx, file_name in enumerate(files):
    file_path = os.path.abspath(os.path.join(root, file_name))
    try:
        file_change_time = os.popen(f'git log -1 --format="%at" -- "{file_path}"').read()
        file_change_time = time.localtime(int(file_change_time.strip()))
    except:
        print(f"{file_name}, error")
        continue
    else:
        result = modifyFileTime(file_path, file_change_time)
        print(f"[{'%.2f' % (idx * 100 / len(files))}%] {file_name}, {'success' if result == 0 else 'error'}")

if quotepath_conf:
    os.popen('git config --global core.quotepath true')
print("done.")

'''
#!/bin/sh
# Linux ver script
# https://github.com/AoEiuV020/owt-server-docker/blob/main/script/touch
. "$(dirname $0)/env"
cd $ROOT
git ls-tree -r --name-only HEAD | while read filename; do 
  unixtime=$(git log -1 --format="%at" -- "${filename}")
  touchtime=$(date -d @$unixtime +'%Y%m%d%H%M.%S')
  touch -t ${touchtime} "${filename}"
done
'''