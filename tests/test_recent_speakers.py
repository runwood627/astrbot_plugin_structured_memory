"""Send synthetic same-nickname messages to an isolated stock AstrBot."""
import asyncio, json, time
import websockets


async def main():
    queue=asyncio.Queue()
    async with websockets.connect('ws://127.0.0.1:6399/ws', additional_headers={'X-Self-ID':'999','X-Client-Role':'Universal'}) as ws:
        async def receive():
            async for raw in ws:
                req=json.loads(raw)
                if req.get('action','').startswith('send_'): await queue.put(req)
                data={'user_id':999,'card':'bot'} if req.get('action')=='get_group_member_info' else {'message_id':1000}
                await ws.send(json.dumps({'status':'ok','retcode':0,'data':data,'echo':req.get('echo')}))
        reader=asyncio.create_task(receive())
        async def send(user, mid, text, mention=False):
            parts=[{'type':'text','data':{'text':text}}]
            if mention: parts.insert(0,{'type':'at','data':{'qq':'999'}})
            msg={'time':int(time.time()),'self_id':999,'post_type':'message','message_type':'group','sub_type':'normal',
                 'message_id':mid,'user_id':user,'group_id':101,'raw_message':text,'font':0,
                 'sender':{'user_id':user,'nickname':'同名','role':'member'},'message':parts}
            await ws.send(json.dumps(msg,ensure_ascii=False))
        await send(201,101,'我选择喝茶。')
        await asyncio.sleep(0.4)
        await send(202,102,'我选择喝咖啡。')
        await asyncio.sleep(0.4)
        await send(203,103,'刚才哪位群友说选择喝咖啡？请直接回答对应的用户 ID。',True)
        result=await asyncio.wait_for(queue.get(),60)
        text=''.join(p.get('data',{}).get('text','') for p in result['params']['message'])
        print('model response:',text)
        assert '202' in text, 'model did not identify the matching synthetic user'
        reader.cancel()

if __name__ == '__main__':
    asyncio.run(main())
