import sys
sys.path.insert(0, '.')
from src.data.kline_fetcher import KlineFetcher

f = KlineFetcher(max_workers=1, delay_per_request=1.0)
# 先测5只
result = f.fetch_batch(['600519','000858','300750','002475','601318'], days=10)
print(f'K线获取: {len(result)}/5')
for sym, data in result.items():
    print(f'  {sym}: {len(data)} days, last={data[-1].date} close={data[-1].close}')
f.clear_cache()
