import time
import asyncio
from functools import wraps
from fastapi.responses import JSONResponse


class Porter:
    def __init__(self, regisger_center: dict, counter_center: dict):
        self._regisger_center = regisger_center
        self._counter_center = counter_center
        self._serving = False

    async def run_serve(self):
        if self._serving == False:
            self._serving = True
            keys = tuple(self._regisger_center.keys())
            sleep_interval_default = 5
            sleep_interval = sleep_interval_default
            while True:
                await asyncio.sleep(sleep_interval)
                sleep_time = time.perf_counter()
                for key in keys:
                    max_bucket, tar_limit = self._regisger_center[key]
                    cur_value = self._counter_center[key]
                    if cur_value < max_bucket:
                        self._counter_center[key] = min(tar_limit * sleep_interval + self._counter_center[key], max_bucket)
                sleep_time = sleep_interval_default - 0.001 - time.perf_counter() + sleep_time # Linux时钟精度较高

class RateLimiter:

    _regisger_center = {'__global__': (250, 125)}
    _counter_center = {'__global__': 250}
    _porter = Porter(_regisger_center, _counter_center)

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._regisger_center = cls._regisger_center
        instance._counter_center = cls._counter_center
        instance._porter = cls._porter
        return instance

    def __init__(self, bucket: int = 150, limits_s: int = 50):
        '''
        以4线程计算，最大负载能力600/s，平均负载能力200/s
        总数据库访问最大 1000 q/s, 平均最大负载 500 q/s
        '''
        self._bucket = bucket
        self._limits_s = limits_s

    def __call__(self, func):
        func_name, global_name = func.__name__, '__global__'
        self._regisger_center[func_name] = (self._bucket, self._limits_s)
        self._counter_center[func_name] = self._bucket

        @wraps(func)
        async def wraper(*args, **kwargs):
            if self._counter_center[func_name] > 0 and self._counter_center[global_name] > 0:
                self._counter_center[func_name] -= 1
                self._counter_center[global_name] -= 1
                return await func(*args, **kwargs)
            return JSONResponse(status_code=503, content="Service Temporarily Unavailable")
        return wraper

    def porter_run_serve(self):
        loop = asyncio.get_running_loop()
        loop.create_task(self._porter.run_serve())
