"""Small paired synthetic end-to-end comparison; never connects to real QQ."""
import asyncio
import json
import time
from pathlib import Path
import websockets

SCENARIOS = [
    ('save_drink', '请记住：我最喜欢的饮料是陈皮气泡水。'),
    ('save_food', '请记住：我不吃芹菜。'),
    ('reset_context', '/reset'),
    ('recall_drink', '请查长期记忆，我最喜欢喝什么？不知道就说不知道。'),
    ('recall_food', '请查长期记忆，我有什么饮食忌口？不知道就说不知道。'),
    ('unknown', '请查长期记忆，我最喜欢什么颜色？不知道就说不知道。'),
]


async def run(label, port):
    queue = asyncio.Queue()
    results = []
    async with websockets.connect(f'ws://127.0.0.1:{port}/ws', additional_headers={'X-Self-ID':'999','X-Client-Role':'Universal'}) as ws:
        async def receive():
            async for raw in ws:
                request = json.loads(raw)
                if request.get('action', '').startswith('send_'):
                    await queue.put(request)
                await ws.send(json.dumps({'status':'ok','retcode':0,'data':{'message_id':1000},'echo':request.get('echo')}))
        task = asyncio.create_task(receive())
        for i, (name, text) in enumerate(SCENARIOS, 101):
            event = {'time':int(time.time()),'self_id':999,'post_type':'message','message_type':'private','sub_type':'friend',
                     'message_id':i,'user_id':203,'raw_message':text,'font':0,'sender':{'user_id':203,'nickname':'Synthetic'},
                     'message':[{'type':'text','data':{'text':text}}]}
            start = time.perf_counter()
            await ws.send(json.dumps(event, ensure_ascii=False))
            try:
                output = await asyncio.wait_for(queue.get(), timeout=90)
                elapsed = round(time.perf_counter()-start, 2)
                answer = ''.join(x.get('data',{}).get('text','') for x in output.get('params',{}).get('message',[]))
            except asyncio.TimeoutError:
                elapsed, answer = 90, '[timeout]'
            results.append({'case':name,'input':text,'answer':answer,'seconds':elapsed})
            print(label, name, elapsed, answer[:180], flush=True)
        task.cancel()
    return results


async def main():
    result = {'description':'Single run, synthetic messages, same DeepSeek chat model. Structured uses SQLite exact fields; LivingMemory uses local bge-m3 and its default recall settings. Not a statistical benchmark.',
              'structured':await run('structured',6399), 'livingmemory':await run('livingmemory',6499)}
    path=Path(__file__).with_name('comparison-results.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved synthetic results:', path, flush=True)


asyncio.run(main())
