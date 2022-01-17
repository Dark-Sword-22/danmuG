import sys, os, re
import datetime

file_dir, file_name = os.path.split(sys.argv[1])
assert os.path.exists(file_dir)
file_name_ext = f"{file_name}.txt"
file_path = os.path.abspath(os.path.join(file_dir, file_name_ext))
assert os.path.exists(file_path)

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.readlines()

time_pat_1 = '%Y-%m-%d %H:%M:%S.%f'
record_time = re.search("[0-9\-:\. ]{25}", content[2]).group()[2:]
record_time = datetime.datetime.strptime(record_time, time_pat_1)

def line_assertion_and_get_msg(text):
    try:
        a = text[text.index(' - ')+3:]
        b = a[a.index(' - ')+3:]
        return b.strip()
    except:
        return ''

def format_seconds(seconds: int) -> str:
        return f"{str(int(seconds // 3600)).zfill(2)}:{str(int((seconds%3600) // 60)).zfill(2)}:{str(int(seconds%60)).zfill(2)}"

output = content[:8]
for line in content:
    msg = line_assertion_and_get_msg(line)
    if msg != '':
        time_stmp = datetime.datetime.strptime(re.search("[0-9\-:\. ]{23}", line).group(), time_pat_1)
        diff_time = min(max(int((time_stmp - record_time).total_seconds()),0),86000)
        output.append(f"{datetime.datetime.strftime(time_stmp, time_pat_1)[:-3]} - {format_seconds(diff_time)} - {msg}\n")

with open(file_path,'w',encoding='utf-8') as f:
    f.writelines(output)

print("\n【合并成功，如上文未出现报错信息，可以按任意键继续。】")
