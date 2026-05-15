import requests
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 全新 Session，不共享
s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://quote.eastmoney.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
})
# 清除之前可能的 cookie
s.cookies.clear()
url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
params = {
    'secid': '1.600519',
    'fields1': 'f1,f2,f3,f4,f5,f6',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
    'klt': '101',
    'fqt': '1',
    'beg': '0',
    'end': '20500101'
}

for attempt in range(3):
    try:
        resp = s.get(url, params=params, timeout=15, verify=False)
        print(f'attempt {attempt}: status={resp.status_code}, len={len(resp.text)}')
        j = resp.json()
        rc = j.get('rc')
        data = j.get('data')
        print(f'  rc={rc}, data is None: {data is None}')
        if data:
            klines = data.get('klines', [])
            name = data.get('name', '')
            print(f'  name={name}, klines={len(klines)}')
            if klines:
                print(f'  first={klines[0]}')
        break
    except Exception as e:
        print(f'attempt {attempt} failed: {type(e).__name__}: {e}')
        time.sleep(1)
