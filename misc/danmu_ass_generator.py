import sys
import os
from pipeit import *
import json
import datetime
from collections import deque
try:
    from loguru import logger
    logger.remove()
    logger.add(sys.stderr, level="INFO", enqueue=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
except:
    from logging import Logger 
    logger = Logger(__name__)



VIDEO_HEIGHT = 1080 # px
VIDEO_WIDTH = 1920 # px
GLOBAL_PADDING_H = 5 # px
FONT_SIZE = 40
TRACK_NUM = int(VIDEO_HEIGHT / (FONT_SIZE + GLOBAL_PADDING_H * 2))

class OrbitalLauncher:

    def __init__(self, track_id: int):
        self.track_id = track_id
        self._height_fix = track_id * (GLOBAL_PADDING_H * 2 + FONT_SIZE) + FONT_SIZE + GLOBAL_PADDING_H
        

    def emit(self, fd: 'TextIOWraper', danmu_time: datetime.datetime, danmu_cmt: str):
        '''
        逻辑：默认每字占50宽度，ascii字符占25宽度
        基础飞行时间12秒，每多2长度加一秒，计算时四舍五入，保留整数。
        正在被占用的发射轨道不能被重复占用。
        '''
        cmt_length = 0
        for char in danmu_cmt:
            if ord(char) > 255:
                cmt_length += 1
            else:
                cmt_length += 0.5
        danmu_st_time_str = f'{danmu_time.strftime("%H:%M:%S.%f")[1:11]}'
        danmu_last_time = 12 + int(cmt_length / 2 + 0.5)
        danmu_ed_time = danmu_time + datetime.timedelta(seconds = danmu_last_time)
        danmu_ed_time_str = f'{danmu_ed_time.strftime("%H:%M:%S.%f")[1:11]}'
        fd.write(f"Dialogue: -1,{danmu_st_time_str},{danmu_ed_time_str},Danmaku,,0000,0000,0000,,{{\\move({VIDEO_WIDTH + cmt_length * FONT_SIZE}, {self._height_fix}, {-cmt_length * FONT_SIZE}, {self._height_fix})\\3c&H000000}}{danmu_cmt}\n")
        cmt_speed = (cmt_length * FONT_SIZE + VIDEO_WIDTH) / danmu_last_time
        safe_distance = (cmt_length * FONT_SIZE * 1.5)
        takes_time = round(safe_distance / cmt_speed if cmt_speed != 0 else 0, 2)
        self._block_until = danmu_time + datetime.timedelta(seconds = takes_time)

    def check_free(self, danmu_time):
        if danmu_time > self._block_until:
            return True 
        return False

    def reset(self):
        self._block_until = datetime.datetime(1999,12,31,23,59,59)

def main():
    if len(sys.argv) != 2:
        logger.error("使用方式不对，将txt文件拖入cmd文件生成ass！")
        input("按回车键退出"); exit()
    try:
        file_path = sys.argv[1]
        if file_path == '':
            # 输入空文件时，默认转码data文件夹内的最近更新文件
            for t_files in os.walk('../data'):
                t_files = t_files[2]; break
            if len(t_files) > 0:
                t_files.sort(key = lambda x:os.stat(f'../data/{x}').st_mtime, reverse = True)
                file_path = os.path.abspath(os.path.join('../data', t_files[0]))
        if file_path[-4:] != '.txt':
            file_path += '.txt'
        file_path = os.path.abspath(file_path)
        file_dir, file_name = os.path.split(file_path)
        assert file_name[:6] == 'danmu-'
    except Exception as e:
        logger.error("拖入的文件不是合法的txt文件")
        input("按回车键退出"); exit()

    

    # 载入配置
    file_name_pure = os.path.splitext(file_name)[0]
    _get = lambda x: x[x.index(':')+1:].strip()
    content = Read(file_path).split('\n')
    streaming_title = file_name_pure[30:]
    danmug_version = _get(content[0])
    streaming_source = _get(content[1])
    record_start_time = datetime.datetime.strptime(_get(content[2]), '%Y-%m-%d %H:%M:%S.%f')
    bvid = os.path.split(_get(content[3]))[1]
    cids = json.loads(_get(content[4])) | Map(str) | list
    time_fix_info = json.loads(_get(content[5]))
    if bvid == '' or len(cids) <= 0 or len(time_fix_info) != len(cids):
        logger.error("视频信息读取错误，文件标注可能有误")
    
    # else
    # 预处理
    danmus_prepare = list()
    danmus_raw = content[8:]
    for row in danmus_raw:
        try:
            assert len(row) > 0 
            p1 = row.index(' - ')
            cmt_time = (datetime.datetime.strptime(row[:p1], '%Y-%m-%d %H:%M:%S.%f') - record_start_time).total_seconds()
            row = row[p1+3:]
            p2 = row.index(' - ')
            cmt = row[p2+3:]
            assert len(cmt) > 0
            danmus_prepare.append([cmt_time, cmt])
        except Exception as e:
            continue

    # 过滤延迟引信
    danmus_struct = {}
    last_video_time = 0
    for pcount, (cid, (video_time, fix_time)) in enumerate(zip(cids, time_fix_info)):
        output_name = f"[{bvid}-P{pcount + 1}-{cid}] {streaming_title}.ass".replace('\\','').replace('/','').replace('<','').replace('>','').replace(':', '').replace('?', '').replace('*', '').replace('"', '').replace('|', '')
        danmus_prepare = danmus_prepare | Map(lambda x: [round(x[0] + fix_time - last_video_time,2), x[1]]) | deque
        target = danmus_struct.setdefault(output_name, [])
        last_video_time = video_time
        if danmus_prepare:
            cursor = danmus_prepare[0][0]
            while cursor <= video_time:
                row = danmus_prepare.popleft()
                if row[0] >= 0:
                    target.append(row)
                if danmus_prepare:
                    cursor = danmus_prepare[0][0]
                else: break
        if len(target) == 0:
            del danmus_struct[output_name]
    
    # 绘制弹幕
    pcount = 0
    lunchers = [OrbitalLauncher(_) for _ in range(TRACK_NUM)]
    for ass_name, danmus in danmus_struct.items():
        pcount += 1
        [luncher.reset() for luncher in lunchers]
        with open(os.path.join(file_dir, ass_name), 'w', encoding='utf-8') as fd:
            ...
        with open(os.path.join(file_dir, ass_name), 'a', encoding='utf-8') as fd:
            fd.write(f"""[Script Info]\n; 秦国弹幕G\n; https://dark-sword-22.pages.dev/\n; https://github.com/Dark-Sword-22/danmuG\n; 弹幕姬版本: {danmug_version}\n; 直播来源地址: {streaming_source}\n; 开始记录时间: {record_start_time}\n; 视频地址: https://www.bilibili.com/video/{bvid}\n; 分P号: P{pcount} - {cids[pcount - 1]}\nTitle: {streaming_title}\nScriptType: v4.00+\nCollisions: Normal\nPlayResX: {VIDEO_WIDTH}\nPlayResY: {VIDEO_HEIGHT}\nTimer: 10.0000\nWrapStyle: 2\nScaledBorderAndShadow: no\n\n""")
            fd.write(f"""[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Danmaku,黑体,{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0.00,0.00,1,1.00,0.00,2,30,30,30,0\n\n""")
            fd.write(f"""[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n""")
            for danmu_time, danmu_cmt in danmus:
                danmu_time = datetime.datetime(2000,1,1,0,0,0) + datetime.timedelta(seconds = danmu_time)
                for luncher in lunchers:
                    if luncher.check_free(danmu_time):
                        luncher.emit(fd, danmu_time, danmu_cmt)
                        break 
                else:
                    continue # 没发出去
        logger.info(f"{ass_name} 处理完成")


if __name__ == '__main__':
    main()