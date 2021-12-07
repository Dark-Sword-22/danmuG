from pyecharts.charts import Bar, Line, Grid
from pyecharts import options as opts
from pyecharts.globals import ThemeType
import datetime
from typing import List, Optional
from bs4 import BeautifulSoup
from cmt_nlp import train_nlp_model, string_query
import requests
from pipeit import *
import json
import os
import sys

def render(x_axis:List[str], yll:List[Optional[float]], ylh:List[Optional[float]], avg: float, cmt_length, time_length, avg_cmt, file_name):
    line = (
        Line()
        .add_xaxis(
            xaxis_data=x_axis,
        )
        .add_yaxis(
            series_name="base-line",
            y_axis=yll,
            label_opts=opts.LabelOpts(is_show=False),
            markpoint_opts=opts.MarkPointOpts(
                data=[
                    opts.MarkPointItem(type_="min", name="最小值"),
                ]
            ),
        )
        .add_yaxis(
            series_name="pata-n-ao",
            y_axis=ylh,
            linestyle_opts=opts.LineStyleOpts(color='orange',width=2),
            markpoint_opts=opts.MarkPointOpts(
                data=[
                    opts.MarkPointItem(type_="max", name="最大值"),
                ]
            ),
            markline_opts=opts.MarkLineOpts(
                data=[opts.MarkLineItem(y=avg, name="平均值")]
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title=file_name, 
                subtitle=f"总时长: {time_length}，总弹幕数量: {cmt_length}，每分钟平均: {avg_cmt}",
                title_link="/danmuG/"
            ),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            xaxis_opts=opts.AxisOpts(type_="category", boundary_gap=False),
            yaxis_opts=opts.AxisOpts(is_scale=True),
            datazoom_opts=[
                opts.DataZoomOpts(range_start=0, range_end=100),
                opts.DataZoomOpts(type_="inside", range_start=0, range_end=100),
            ],   
        )
    )
    grid = Grid(init_opts=opts.InitOpts(theme=ThemeType.LIGHT,width="1900px",height="900px"))
    grid.add(line, grid_opts = opts.GridOpts(pos_left='4%', pos_right='4%'))
    return grid

def jinja222(extra_head, main_chart_div, ptao, extra_scripts, tag_res):
    template = (
        Read(os.path.abspath('./templates/html22-2.html'))
        .replace('{{extra_head}}', str(extra_head))
        .replace('{{main_chart_div}}', str(main_chart_div))
        .replace('{{trs_data}}', f"let trsJsonStr={repr(json.dumps(ptao))}")
        .replace('{{extra_scripts}}', str(extra_scripts))
        .replace('{{tag_res_data}}', f"let jsonStr={repr(json.dumps(tag_res))}")
    )
    return template

def jinja22(struct, superman_data):
    template = (
        Read(os.path.abspath('./templates/html22.html'))
        .replace("{{main_data}}", repr(json.dumps(struct)))
        .replace("{{superman_data}}", repr(json.dumps(superman_data)))
    )
    return template


def main(mode):
    src_dir = os.path.abspath('./data')
    dst_dir = os.path.abspath('./docs')

    src_files = []
    for src_files in os.walk(src_dir):
        src_files = src_files[2] | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.txt') | Map(lambda x: os.path.splitext(x)[0]) | set 
        break
    dst_files = []
    for dst_files in os.walk(dst_dir):
        dst_files = dst_files[2] | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.html') | Map(lambda x: os.path.splitext(x)[0]) | set 
        break
    if mode == '0':
        diff_files = sorted(src_files.difference(dst_files) | Map(lambda x:x+'.txt') | list)
    elif mode == '1':
        diff_files = src_files | Map(lambda x:x+'.txt') | list
        diff_files.sort(key = lambda x: datetime.datetime.strptime(x[6:6+23], '%Y-%m-%d-%H-%M-%S-%f'), reverse = True)
        diff_files = [diff_files[0],]
    else:
        raise

    drop_list = []
    for file_name in diff_files:

        file_path = os.path.join(src_dir, file_name)
        text = Read(file_path).split('\n') | Filter(lambda x:x.strip() != '') | list
        st_time = datetime.datetime.strptime(text[2][text[2].index(':') + 2:-4], '%Y-%m-%d %H:%M:%S')
        if len(text) <= 50:
            drop_list.append(file_path)
            continue
        '''
        理论上应该是公用同一字典即可学习，但是测试了一下发现效果居然受语料库输入顺序影响，也是搞不太清楚为什么
        '''
        processed_corpus, lda, index, dictionary = train_nlp_model(src_dir, file_name, passes = 5, file_count = 1)


        text_backup = text[min(len(text) - 1, 8):] | Map(lambda x: (datetime.datetime.strptime(x[:19], '%Y-%m-%d %H:%M:%S'), x[37:])) | list 
        text = text[min(len(text) - 1, 8):] | Map(lambda x: (datetime.datetime.strptime(x[:19], '%Y-%m-%d %H:%M:%S') - st_time).total_seconds()) | list
        cmt_length = len(text)
        time_length = text[-1] - text[0]
        avg_cmt = round(cmt_length / (time_length / 60),2)
        time_length = f"{int(time_length//3600)}h{int((time_length%3600)//60)}min{int(time_length%60)}s"

        file_size = os.stat(file_path).st_size
        if file_size >= (1024*1024):
            file_size = f"{round(file_size / 1024 / 1024,2)}MB"
        elif file_size >= 1024:
            file_size = f"{round(file_size / 1024 ,2)}KB"
        else:
            file_size = f"{file_size}B"
        x_length = int(text[-1] // 5 + 1)
        tab = []
        for _ in range(x_length):
            tab.append(0)
        for cmt in text:
            tab[int(cmt // 5)] += 1
        # Smooth
        for idx in range(len(tab) - 1, 2, -1):
            tab[idx] = (tab[idx] + tab[idx - 1] + tab[idx - 2] + tab[idx - 3]) / 4
        avg = round(sum(tab) / len(tab) * 1.8, 2)
        avg2 = round(sum(tab) / len(tab) * 3, 2)
        # Split high & low
        yll, ylh = ['-', ], ['-', ]
        x_axis = ['00:00:00']
        ptao = []
        last_status = tab[0] >= avg
        last_status2 = tab[0] >= avg2
        max_cmt_l = 110
        cmt_cur = 0
        for idx in range(1, len(tab)):
            if tab[idx] >= avg:
                ylh.append(tab[idx])
                ylh[-2] = tab[idx - 1]
                yll.append('-')
                if not last_status:
                    yll[-1] = tab[idx]
            else:
                ylh.append('-')
                yll.append(tab[idx])
                yll[-2] = tab[idx - 1]
                if last_status:
                    ylh[-1] = tab[idx]
            last_status = tab[idx] >= avg
            if tab[idx] > avg2 and not last_status2:
                tmp_cmt_stack = []
                converted_time_range = (st_time + datetime.timedelta(seconds = (idx-3) * 5), st_time + datetime.timedelta(seconds = (idx+8) * 5))
                cmt_cur = 0
                while cmt_cur<len(text_backup) and text_backup[cmt_cur][0] <= converted_time_range[1]:
                    if converted_time_range[0] <= text_backup[cmt_cur][0]:
                        tmp_cmt_stack.append(text_backup[cmt_cur][1])
                    cmt_cur+=1
                _buffer = '，'.join(tmp_cmt_stack)
                _buffer = string_query(_buffer, 10, False, processed_corpus, lda, index, dictionary)

                if len(_buffer) >= max_cmt_l:
                    _buffer = _buffer[:max_cmt_l] + '...'
                cmt_max = max(tab[idx-1:min(idx+6, len(tab))])
                ptao.append((f"{str(int(idx*5//3600)).zfill(2)}:{str(int((((idx*5)%3600)//60))).zfill(2)}:{str(int(((idx*5)%60))).zfill(2)}", str(st_time + datetime.timedelta(seconds = idx*5)), cmt_max, _buffer))
                
            last_status2 = tab[idx] >= avg2
            x_axis.append(f"{str(int(idx*5//3600)).zfill(2)}:{str(int((((idx*5)%3600)//60))).zfill(2)}:{str(int(((idx*5)%60))).zfill(2)}")

        if len(ptao) < 15:
            # 降准
            avg3 = round(sum(tab) / len(tab) * 2.5, 2)
            ptao = []
            cmt_cur = 0
            last_status3 = tab[0] >= avg3
            for idx in range(1, len(tab)):
                if tab[idx] > avg3 and not last_status3:
                    tmp_cmt_stack = []
                    converted_time_range = (st_time + datetime.timedelta(seconds = (idx-3) * 5), st_time + datetime.timedelta(seconds = (idx+8) * 5))
                    cmt_cur = 0
                    while cmt_cur<len(text_backup) and text_backup[cmt_cur][0] <= converted_time_range[1]:
                        if converted_time_range[0] <= text_backup[cmt_cur][0]:
                            tmp_cmt_stack.append(text_backup[cmt_cur][1])
                        cmt_cur+=1
                    _buffer = '，'.join(tmp_cmt_stack)
                    _buffer = string_query(_buffer, 10, False, processed_corpus, lda, index, dictionary)

                    if len(_buffer) >= max_cmt_l:
                        _buffer = _buffer[:max_cmt_l] + '...'
                    
                    cmt_max = max(tab[idx-1:min(idx+6, len(tab))])
                    ptao.append((f"{str(int(idx*5//3600)).zfill(2)}:{str(int((((idx*5)%3600)//60))).zfill(2)}:{str(int(((idx*5)%60))).zfill(2)}", str(st_time + datetime.timedelta(seconds = idx*5)), cmt_max, _buffer))
                last_status3 = tab[idx] >= avg3

        # nlp topic part
        if len(ptao) > 1:
            last_he_time = datetime.datetime.strptime(ptao[0][0],'%H:%M:%S')
            show_text_list = [(last_he_time, ptao[0][2]),]
            anchor_time = datetime.datetime.strptime('0:00:00','%H:%M:%S')
            for higherg in ptao[1:]:
                curt_he_time = datetime.datetime.strptime(higherg[0],'%H:%M:%S')
                t_diff = (curt_he_time - last_he_time).total_seconds()
                if t_diff >= 60 * 6.5:
                    # 与上次高能间隔六分钟以上
                    show_text_list.append((curt_he_time, higherg[2]))
                last_he_time = curt_he_time
            show_text_list = show_text_list | Map(lambda x: (int((x[0] - anchor_time).total_seconds() // 5), x[1])) | list 
            if show_text_list:
                ctime_range_list = []
                for sidx, max_cmt in show_text_list:
                    for cidx in range(sidx, min(sidx + 10, len(tab)), 1):
                        if tab[cidx] == max_cmt:
                            break
                    else:
                        # 理论上这种情况不应该发生
                        raise 
                    converted_time_range = (st_time + datetime.timedelta(seconds = (cidx-3) * 5), st_time + datetime.timedelta(seconds = (cidx+8) * 5), cidx)
                    ctime_range_list.append(converted_time_range)
                cmt_cur = 0
                tag_res = []
                for converted_time_st, converted_time_ed, cidx in ctime_range_list:
                    content_lst = []
                    while cmt_cur < len(text_backup) and text_backup[cmt_cur][0] <= converted_time_ed:
                        if text_backup[cmt_cur][0] >= converted_time_st:
                            content_lst.append(text_backup[cmt_cur][1])
                        cmt_cur += 1
                    content = '，'.join(content_lst)
                    tags = string_query(content, 6, True, processed_corpus, lda, index, dictionary)
                    seconds = cidx * 5
                    tag_res.append((tags,(int(seconds // 3600), int((seconds%3600) // 60), int(seconds%60))))

        chart_html = render(x_axis,  yll,  ylh,  avg, cmt_length, time_length, avg_cmt, file_name).render_embed()
        chart_soup = BeautifulSoup(chart_html, 'lxml')
        chart_head = str(chart_soup.find_all('script')[0]).replace('https://assets.pyecharts.org/assets/echarts.min.js','https://cdn.jsdelivr.net/npm/echarts@4.9.0/dist/echarts.min.js')
        chart_div = chart_soup.find('div')
        chart_script = chart_soup.find_all('script')[-1]
        

        rendered_html = jinja222(chart_head, chart_div, ptao, chart_script, tag_res)
        Write(os.path.join(dst_dir, os.path.splitext(file_name)[0] + '.html'), rendered_html)

    for file_name in drop_list:
        file_path = os.path.join(src_dir, file_name)
        try:
            os.remove(file_path)
        except:
            ...

    dst_files = []
    for dst_files in os.walk(dst_dir):
        dst_files = dst_files[2] | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.html') | Map(lambda x: os.path.splitext(x)[0]) | list 
        dst_files.sort()
        break

    struct = []
    for file_name in dst_files:
        source_path = os.path.join(src_dir, file_name+'.txt')
        stream_name = os.path.splitext(file_name)[0][30:]
        file_html = file_name + '.html'
        file_url = "https://dark-sword-22.github.io/danmuG/"+file_html
        file_size = os.stat(source_path).st_size
        if file_size >= (1024*1024):
            file_size = f"{round(file_size / 1024 / 1024, 2)}MB"
        elif file_size >= 1024:
            file_size = f"{round(file_size / 1024 , 2)}KB"
        else:
            file_size = f"{file_size}B"
        cmt_length = max(len(Read(source_path).split('\n')) - 8, 0)
        file_create_time = datetime.datetime.strptime(file_name[6:6+23], '%Y-%m-%d-%H-%M-%S-%f')
        struct.append({
            'full_name': file_name,
            'display_name': stream_name,
            'size': file_size,
            'length': cmt_length,
            'href': file_url,
            'finished': None,
            'datetime': str(file_create_time)[:19],
            'cttime': file_create_time,
        })

    struct.sort(key = lambda x:x['cttime'], reverse=True)
    finished_data = json.loads(requests.get('https://dog.464933.xyz/api/fetch-accomplishment-rate').text)
    for key, value in finished_data.items():
        for _ in struct:
            if _['full_name'][:29] == key:
                _['finished'] = value
    for _ in struct: 
        del _['cttime']
        if _['finished']:
            _['health'] = min(max(round(_['finished'] *100/ _['length'],1),0),100)
        else:
            _['health'] = "NaN"
        del _['finished']
    superman_data = json.loads(requests.get('https://dog.464933.xyz/api/fetch-superman').text)
    index_html = jinja22(struct, superman_data)
    Write(os.path.join(dst_dir, 'index.html'), index_html)
    Write('README.md', Read('README.md') + ' ')

try:
    if sys.argv[1] == '1':
        mode = '1'
    else:
        mode = '0'
except:
    mode = '0'
main(mode = mode)
