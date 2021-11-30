from pipeit import *
import os
import sys
import re
import datetime
import shutil

if len(sys.argv) < 2:
    raise RuntimeError("至少输入一个文件")

in_file = sys.argv[1]
file_dir = os.path.split(in_file)[0]

for files in os.walk(file_dir):
    files = (
        files[2] 
        | Filter(lambda x:re.match('[\d]{4}-[\d]{2}-[\d]{2}-[\d]{2}-[\d]{2}-[\d]{2}.ts',x))
        | list
    ); break

files.sort(key = lambda x: datetime.datetime.strptime(x, '%Y-%m-%d-%H-%M-%S.ts'))
files = files | Map(lambda x: os.path.join(file_dir, x)) | list
if len(files) > 0:
    with open(f'{os.path.splitext(files[0])[0]}.mp4', 'wb') as merged:
        for file_path in files:
            with open(file_path, 'rb') as mergefile:
                shutil.copyfileobj(mergefile, merged)
    for file_path in files:
        try:
            os.remove(file_path)
        except Exception as e:
            raise e