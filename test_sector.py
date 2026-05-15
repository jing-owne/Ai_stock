import requests, urllib3
urllib3.disable_warnings()
s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/',
})
r = s.get('https://push2.eastmoney.com/api/qt/clist/get', params={
    'pn':'1','pz':'5','po':'1','np':'1',
    'fs':'m:90+t:2','fields':'f2,f3,f4,f12,f14'
}, timeout=10, verify=False)
print('status:', r.status_code)
j = r.json()
items = j.get('data',{}).get('diff',[])
print('items:', len(items))
for i in items[:3]:
    name = i.get('f14','')
    pct = i.get('f3',0)
    print(f'  {name}: {pct}%')
s.close()
