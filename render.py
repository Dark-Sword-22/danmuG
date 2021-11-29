from pyecharts.charts import Bar, Line, Grid
from pyecharts import options as opts
from pyecharts.globals import ThemeType
import datetime
from typing import List, Optional
from bs4 import BeautifulSoup
from pipeit import *
import os

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
            title_opts=opts.TitleOpts(title=file_name, subtitle=f"总时长: {time_length}，总弹幕数量: {cmt_length}，每分钟平均: {avg_cmt}"),
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

def jinja222(extra_head, main_chart_div, ptao, extra_scripts):
    template = Read(os.path.abspath('./templates/html22-2.html'))
    tr_tmplate ='''
                    <tr>
                      <td class="px-6 py-4 whitespace-nowrap">
                        <div class="text-sm text-gray-500">{ttime}</div>
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap">
                        <div class="flex items-center">
                            <div class="text-sm font-medium text-gray-900">
                              {dtime}
                            </div>
                        </div>
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap">
                        <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                          {cmtl}
                        </span>
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap">
                        <div class="text-sm text-gray-500">{cmtc}</div>
                      </td>
                    </tr>'''
    trs = ''.join([tr_tmplate.format(dtime = dtime, ttime = ttime, cmtl = cmtl, cmtc = cmtc) for dtime, ttime, cmtl, cmtc in ptao])
    template = (
        template.replace('{{extra_head}}', str(extra_head))
        .replace('{{main_chart_div}}', str(main_chart_div))
        .replace('{{trs}}', str(trs))
        .replace('{{extra_scripts}}', str(extra_scripts))
    )
    return template

def jinja22(fl):
    template = Read(os.path.abspath('./templates/html22.html'))
    tr_tmplate ='''
            <tr>
              <td valign="top"></td>
              <td><a href="{url}" class="mr-8 text-blue-600 underline">{hname}</a>
              </td><td align="right"><span class="mr-8">{realt}</span></td>
              <td align="right"><span class="mr-8">{size}</span></td>
              <td align="right">{length}</td>
            </tr>'''
    filelist_tr = ''.join([tr_tmplate.format(url=url, hname=hname, realt=realt, size=size, length=length) for url, hname, realt, size, length in fl])
    template = template.replace('{{filelist_tr}}', filelist_tr)
    return template

def main():
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

    diff_files = sorted(src_files.difference(dst_files) | Map(lambda x:x+'.txt') | list)
    drop_list = []
    for file_name in diff_files:
        file_path = os.path.join(src_dir, file_name)
        text = Read(file_path).split('\n') | Filter(lambda x:x.strip() != '') | list
        st_time = datetime.datetime.strptime(text[3], '%Y-%m-%d %H:%M:%S')
        if len(text) <= 10:
            drop_list.append(file_path)
            continue
        text_backup = text[min(len(text) - 1, 5):] | Map(lambda x: (datetime.datetime.strptime(x[:19], '%Y-%m-%d %H:%M:%S'), x[22:])) | list 
        text = text[min(len(text) - 1, 5):] | Map(lambda x: (datetime.datetime.strptime(x[:19], '%Y-%m-%d %H:%M:%S') - st_time).total_seconds()) | list
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
                _buffer = ''
                while cmt_cur < len(text_backup) and len(_buffer) < max_cmt_l:
                    if text_backup[cmt_cur][0] >= (st_time + datetime.timedelta(seconds = idx*5+5)):
                        if _buffer == '':
                            _buffer += f'{text_backup[cmt_cur][1]}'
                        else:
                            _buffer += f', {text_backup[cmt_cur][1]}'
                    cmt_cur += 1
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
                    _buffer = ''
                    while cmt_cur < len(text_backup) and len(_buffer) < max_cmt_l:
                        if text_backup[cmt_cur][0] >= (st_time + datetime.timedelta(seconds = idx*5+5)):
                            if _buffer == '':
                                _buffer += f'{text_backup[cmt_cur][1]}'
                            else:
                                _buffer += f', {text_backup[cmt_cur][1]}'
                        cmt_cur += 1
                    _buffer = _buffer[:max_cmt_l] + '...'
                    cmt_max = max(tab[idx-1:min(idx+6, len(tab))])
                    ptao.append((f"{str(int(idx*5//3600)).zfill(2)}:{str(int((((idx*5)%3600)//60))).zfill(2)}:{str(int(((idx*5)%60))).zfill(2)}", str(st_time + datetime.timedelta(seconds = idx*5)), cmt_max, _buffer))
                last_status3 = tab[idx] >= avg3


        chart_html = render(x_axis,  yll,  ylh,  avg, cmt_length, time_length, avg_cmt, file_name).render_embed()
        chart_soup = BeautifulSoup(chart_html, 'lxml')
        chart_head = str(chart_soup.find_all('script')[0]).replace('https://assets.pyecharts.org/assets/echarts.min.js','https://cdn.jsdelivr.net/npm/echarts@4.9.0/dist/echarts.min.js')
        chart_div = chart_soup.find('div')
        chart_script = chart_soup.find_all('script')[-1]
        

        rendered_html = jinja222(chart_head, chart_div, ptao, chart_script)
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

    fl = []
    for file_name in dst_files:
        source_path = os.path.join(src_dir, file_name+'.txt')
        file_html = file_name + '.html'
        file_url = "https://dark-sword-22.github.io/danmuG/"+file_html
        file_size = os.stat(source_path).st_size
        if file_size >= (1024*1024):
            file_size = f"{round(file_size / 1024 / 1024, 2)}MB"
        elif file_size >= 1024:
            file_size = f"{round(file_size / 1024 , 2)}KB"
        else:
            file_size = f"{file_size}B"
        cmt_length = max(len(Read(source_path).split('\n')) - 6, 0)
        file_create_time = datetime.datetime.strptime(file_name[6:6+19], '%Y-%m-%d-%H-%M-%S')
        fl.append((file_url, file_html, file_create_time, file_size, cmt_length))
    fl.sort(key = lambda x:x[2], reverse = True)
    index_html = jinja22(fl)
    Write(os.path.join(dst_dir, 'index.html'), index_html)

main()
