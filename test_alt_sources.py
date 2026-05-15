"""测试新浪财经K线接口"""
import requests
import json

# 新浪财经日K线接口
url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
params = {
    "symbol": "sh600519",
    "scale": "240",  # 日K
    "ma": "no",
    "datalen": "10",
}

try:
    r = requests.get(url, params=params, timeout=10)
    print(f"status: {r.status_code}, len: {len(r.text)}")
    data = json.loads(r.text)
    print(f"records: {len(data)}")
    for d in data[-3:]:
        print(f"  {d['day']} close={d['close']} vol={d['volume']}")
except Exception as e:
    print(f"新浪接口失败: {type(e).__name__}: {e}")

# 网易财经日K线
print()
url2 = "http://quotes.money.163.com/service/chddata.html"
params2 = {
    "code": "0600019",  # 0=沪市 1=深市
    "start": "20260501",
    "end": "20260515",
    "fields": "TCLOSE;HIGH;LOW;TOPEN;VOTURNOVER;CHG;PCHG;TURNOVER",
}
try:
    r2 = requests.get(url2, params=params2, timeout=10)
    print(f"网易 status: {r2.status_code}, len: {len(r2.text)}")
    lines = r2.text.strip().split('\n')
    print(f"lines: {len(lines)}")
    for l in lines[:5]:
        print(f"  {l[:100]}")
except Exception as e:
    print(f"网易接口失败: {type(e).__name__}: {e}")
