"""Read-only official MCP gateway; credentials stay in the backend."""
import datetime as dt
import json
import os
import threading
import urllib.error
from pathlib import Path
from mcd_transport import Client

TZ=dt.timezone(dt.timedelta(hours=8))
ALLOWED=frozenset({'query-nearby-stores','query-meals','query-meal-detail','calculate-price'})
AUDIT=Path(os.environ.get('PHM_AUDIT',str(Path(__file__).parent/'mcp-audit.jsonl')))
AUDIT_LOCK=threading.Lock()
def timestamp():return dt.datetime.now(TZ).isoformat(timespec='seconds')
class LiveError(Exception):pass

class Gateway:
    def __init__(self):self.local=threading.local()
    def begin(self):self.local.client=None
    def call(self,name,args):
        if name not in ALLOWED:raise LiveError('当前版本仅支持查询，没有下单或付款功能。')
        try:
            client=getattr(self.local,'client',None)
            if client is None:
                client=Client();client.initialize();self.local.client=client
            result=client.send('tools/call',{'name':name,'arguments':args})
            block=result.get('result',{});data=block.get('structuredContent')
            if 'error' in result or block.get('isError') or not isinstance(data,dict):raise LiveError('麦当劳未返回可用的查询结果，请重新选择门店、时间和套餐。')
            if data.get('success') is False or data.get('code') not in (None,0,200,'200'):
                raise LiveError(str(data.get('message') or '麦当劳查询失败，请重试。')[:160])
            audit={'at':timestamp(),'tool':name,'storeCode':args.get('storeCode'),'reservationDate':args.get('reservationDate'),'productCode':args.get('code'),'traceId':data.get('traceId'),'sourceTime':data.get('datetime')}
            with AUDIT_LOCK,AUDIT.open('a',encoding='utf-8') as f:f.write(json.dumps(audit,ensure_ascii=False)+'\n')
            return data
        except LiveError:raise
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403):raise LiveError('麦当劳 Token 已失效或权限不足，请更新本机 Token。') from None
            if exc.code==429:raise LiveError('查询过于频繁，请稍后重试。') from None
            raise LiveError('麦当劳接口暂不可用，请稍后重试。') from None
        except (FileNotFoundError,AttributeError):raise LiveError('未找到可用的本机 MCP 配置，请先配置 Token。') from None
        except Exception:raise LiveError('连接麦当劳接口失败，请检查网络与本机 Token 后重试。') from None
