from pipeit import *
import os
import datetime
import sqlite3
import ujson as json
import gzip

def check_txt_has_url(file_name):
    with open(os.path.join(os.path.abspath('../data/'), file_name), 'r', encoding='utf-8') as f:
        for _ in range(4):
            line = f.readline()
        if line.strip() == '' or line.strip() == '视频地址:':
            return False
        return True

def sql_read_all_lines(conn, db_name):
    cur = conn.cursor()
    cur.execute(f"SELECT id, hash, cmt_time, send_time, content, bvid, cid, status, fail_count, rnd FROM `{db_name}` order by id")
    data = cur.fetchall()
    return data 

def sql_drop_table(conn, db_name):
    cur = conn.cursor()
    cur.execute(f"DROP TABLE `{db_name}`")
    conn.commit()

def dump_data(db_name, data):
    # 格式 id, hash, cmt_time, send_time, content, bvid, cid, status, fail_count, rnd
    with open(os.path.join(os.path.abspath('.'), f'{db_name}.json.gz'), 'wb') as f:
        f.write(gzip.compress(json.dumps(data).encode()))

def main():
    data_dir = os.path.abspath('../data/')
    for files in os.walk(data_dir):
        files = (
            files[2] 
            | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.txt') 
            # | Map(lambda x:x[:29])
            | list 
        )
    files.sort(key = lambda x: datetime.datetime.strptime(x[6:6+23], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)
    if len(files) > 22: files = files[22:]
    files_name_map = dict(zip(files | Map(lambda x:x[:29]), files))
    files_set = set(files | Map(lambda x:x[:29]))
    for files in os.walk('.'):
        archives_set = (files[2]
            | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.gz') 
            | Map(lambda x:x[:29])
            | set
        )
    file_to_copy = list(files_set - archives_set)
    file_to_copy.sort(key = lambda x: datetime.datetime.strptime(x[6:6+23], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)

    if not os.path.exists(os.path.join(os.path.abspath('../thunder/'), 'sqlite.db')):
        raise FileNotFoundError()
    conn = sqlite3.connect(os.path.join(os.path.abspath('../thunder/'), 'sqlite.db'))
    for idx, db_name in enumerate(file_to_copy):
        if check_txt_has_url(files_name_map[db_name]):
            data = sql_read_all_lines(conn, db_name)
            if data and len(data) > 0:
                dump_data(db_name, data)
                sql_drop_table(conn, db_name)
                print(f"[{'%.2f' % (idx * 100 / len(file_to_copy))}%] {db_name} done.")
    cur = conn.cursor()
    cur.execute("VACUUM")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    main()
