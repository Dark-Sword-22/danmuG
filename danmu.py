from bs4 import BeautifulSoup
from collections import deque
import time
import datetime
from pipeit import *
from selenium import webdriver
from selenium.webdriver.common.by import By
from loguru import logger
import re
import os
import sys

VERSION = '0.1.0'

class CmtBuffer:

    def __init__(self, mval: int = 200, flood_control: int = 5, set_length = 50):
        '''
        deque里储存的是原始数据，不是flt后的数据
        '''
        self._buffer = deque()
        self._recent_set = deque()
        self._set_length = set_length
        self._mval = mval
        self._flood_control = flood_control

    def append(self, msg):
        self._buffer.append(msg)
        self._recent_set.append(msg)
        while len(self._recent_set) > self._set_length:
            self._recent_set.popleft()
        self._poper()

    def extend(self, lst):
        self._buffer.extend(lst)
        self._recent_set.extend(lst)
        while len(self._recent_set) > self._set_length:
            self._recent_set.popleft()
        self._poper()

    def _poper(self):
        while len(self._buffer) > self._mval:
            self._buffer.popleft()

    def undup(self, raw_lst):
        # 匹配并返回截断号，比如输入的raw_lst从第0项开始是新的，就返回0，从3开始是新的就返回3
        # 全是旧的，返回-1
        length = len(raw_lst)
        rev_raw_lst = raw_lst[::-1]
        loop_length = min(length, len(self._buffer))
        if loop_length > 0:
            for cursor_idx in range(length):
                for check_idx in range(min(loop_length, length - cursor_idx)):
                    if rev_raw_lst[cursor_idx + check_idx] != self._buffer[-check_idx - 1]:
                        break 
                else:
                    # 完全匹配末尾项成功
                    if cursor_idx == 0:
                        return -1
                    return length - cursor_idx
            return 0
        else:
            if len(self._buffer) == 0:
                return 0
            else:
                return -1

    def autoupdate(self, raw_lst):
        idx = self.undup(raw_lst)
        if idx != -1:
            raw_lst = raw_lst[idx:]
            if idx == 0 or len(raw_lst) > self._flood_control:
                # 目前观察只有返回全序列时候会出现重复bug，此时剔除重复弹幕
                raw_lst_backup = raw_lst[:]
                raw_lst = []
                for _ in raw_lst_backup:
                    if _ not in self._recent_set:
                        raw_lst.append(_)
            self.extend(raw_lst)
            new_lst = raw_lst | Map(self._fltstr) | Filter(lambda x:len(x) > 0) | tuple
            if len(new_lst) > self._flood_control:
                new_lst = new_lst[-self._flood_control:]
            return new_lst
        else:
            return None

    def _fltstr(self, string):
        return string.replace('\r\n','\n').replace('\n',' ').strip()

class Writer:

    def __init__(self, watch_url, title):
        '''
        弹幕姬版本: 0.1.0
        直播来源地址: ...
        开始记录时间:
        2020-01-01 22:22:22

        ================================================== * 50
        2021-11-24 00:31:39 - 
        '''
        title = title.replace('/','').replace('\\','').replace('?','').replace(' ','')
        self.file_name_time = str(datetime.datetime.now() + datetime.timedelta(seconds = 3600*8))[:19]
        self.file_name = os.path.join(os.path.abspath('./data/'), f'danmu-{self.file_name_time}-{title}.txt'.replace(':', '-').replace(' ','-'))
        with open(self.file_name,'w',encoding='utf-8') as f:
            f.write(f"弹幕姬版本: {VERSION}\n")
            f.write(f"直播来源地址: {watch_url}\n")
            f.write(f"开始记录时间:\n")
            f.write(f"{self.file_name_time}\n")
            f.write(f"\n{'='*50}\n")

    def update(self, words):
        with open(self.file_name,'a',encoding='utf-8') as f:
            f.write(f"{str(datetime.datetime.now() + datetime.timedelta(seconds = 3600*8))[:19]} - {words}\n")

def git_push():
    os.system("git add -A")
    os.system('git commit -m "弹幕更新"')
    os.system("git push")
    logger.debug("Git pushed")
    
def git_pull():
    os.system("git checkout .")
    os.system("git pull")
    logger.debug("Git pulled")

def main_watching_loop(browser, watch_url, refresh_interval, close_threshold):
    browser.refresh()
    browser.implicitly_wait(5)
    browser.get(watch_url)
    browser.implicitly_wait(10)

    cmt_buffer = CmtBuffer()

    title = stream_title(browser.find_element(By.XPATH, '//*').get_attribute("outerHTML"))
    logger.debug(f"直播间标题, {title}")
    writer = Writer(watch_url, title)

    logger.info("欢迎使用网易cc弹幕姬，监视弹幕列表中")
    logger.info('=' * 20)

    latest_update_time = time.time()
    while True:
        # 这里的xpath的1是指第0号元素
        # html = browser.find_element_by_xpath("//body/div[1]/div[contains(@class,'page-right-container')][1]/div[contains(@class,'main-container')][1]/div[1]/div[contains(@class,'breakroom-main-container')][1]/div[1]/div[1]/div[contains(@class,'player-area')][1]").get_attribute("outerHTML")
        current_time = time.time()
        if (current_time - latest_update_time) >= close_threshold:
            # 直播结束
            logger.debug("长时间无弹幕，直播结束")
            break

        st_time = current_time
        try:
            area_html = browser.find_element(By.CSS_SELECTOR, '.player-area').get_attribute("outerHTML")
        except:
            area_html = None
        if area_html:
            area_soup = BeautifulSoup(area_html, 'lxml')
            itv_new_cmts_raw = area_soup.find_all('div', {'class': 'cmt'}) | Map(lambda x:x.text) | list
            if len(itv_new_cmts_raw) > 0:
                new_cmts = cmt_buffer.autoupdate(itv_new_cmts_raw)
                if new_cmts:
                    for _ in new_cmts:
                        writer.update(_)
                        latest_update_time = time.time()
                        logger.info(f"cmt - {_}")

        sleep_time = max(refresh_interval - (time.time() - st_time), 0)
        time.sleep(sleep_time)

def stream_title(full_html):
    res = re.search('<div class="js-onlive-title-normal nick onlive-setting-name">.+?</div>', full_html)
    if res:
        tt = res.group()
        tt = tt[tt.index('>') + 1:len(tt) - tt[::-1].index('<') - 1]
        return tt 
    else:
        return "标题获取错误"

def check_streming(browser, watch_url, check_refresh_interval):
    browser.refresh()
    browser.implicitly_wait(5)
    browser.get(watch_url)
    browser.implicitly_wait(int(check_refresh_interval // 2))
    time.sleep(int(check_refresh_interval // 5))
    try:
        page_html = browser.find_element(By.ID, "live-wrapper").get_attribute("outerHTML")
        soup = BeautifulSoup(page_html, 'lxml')
        nolive_recommend_lasttime = re.search('<div class="nolive-recommend-lasttime">上次直播时间.+?前</div>', str(soup))
        already_freshed = soup.find('div', {'class', 'ccplayer-showEnterRoom'})
        if already_freshed and not nolive_recommend_lasttime:
            return True
        else:
            return False
    except:
        return False

def main(
        watch_url,
        refresh_interval,
        check_refresh_interval,
        close_threshold,
    ):
    logger.debug("主程序启动")
    logger.info(f"监视地址： {watch_url}")

    # create chrome window
    chrome_options = webdriver.ChromeOptions()
    # chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless')
    # chrome_options.add_argument('--disable-gpu')
    # chrome_options.add_argument('--disable-dev-shm-usage')
    # chrome_options.add_argument('--profile-directory=Default')
    # chrome_options.add_argument('--user-data-dir=/root/.config/google-chrome')

    browser = webdriver.Chrome(options=chrome_options)
    # browser.set_window_size(1920,1080)

    # loop
    while True:
        logger.debug("New Loop")

        while True:
            logger.debug("Detact if streaming")
            st_time = time.time()
            streaming = check_streming(browser, watch_url, check_refresh_interval)
            if streaming:
                logger.info("检测到直播间已开播")
                break
            logger.info("检测到直播间未开播")
            sleep_time = max(check_refresh_interval * 2 - (time.time() - st_time), 0)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        #
        git_pull()

        # 获取直播间弹幕
        main_watching_loop(browser, watch_url, refresh_interval, close_threshold)

        # 上传
        git_push()


watch_url = 'https://cc.163.com/361433/'
try:
    with open('watch_url.txt','r',encoding='utf-8') as f:
        watch_url = f.read()
        watch_url = watch_url.strip()
except:
    watch_url = 'https://cc.163.com/361433/'

logger.add("log_1.txt", level="DEBUG", rotation="5 MB")
# logger.remove()
# logger.add(sys.stdout, level = 'DEBUG')

main(
    watch_url = watch_url,
    refresh_interval = 0.2,
    check_refresh_interval = 30,
    close_threshold = 100,
)
