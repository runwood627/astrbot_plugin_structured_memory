"""Synthetic group flow against the isolated stock AstrBot instance."""
import asyncio, json, time
import websockets

async def main():
    queue = asyncio.Queue()
    async with websockets.connect('ws://127.0.0.1:6399/ws', additional_headers={'X-Self-ID':'999','X-Client-Role':'Universal'}) as ws:
        async def receive():
            async for raw in ws:
                req=json.loads(raw)
                if req.get('action','').startswith('send_'):
                    await queue.put(req)
                name=req.get('action')
                data={'user_id':999,'card':'bot'} if name=='get_group_member_info' else {'message_id':1000}
                await ws.send(json.dumps({'status':'ok','retcode':0,'data':data,'echo':req.get('echo')}))
        reader=asyncio.create_task(receive())
        async def turn(user, mid, text, mention=False):
            parts=[{'type':'text','data':{'text':text}}]
            if mention: parts.insert(0,{'type':'at','data':{'qq':'999'}})
            event={'time':int(time.time()),'self_id':999,'post_type':'message','message_type':'group','sub_type':'normal',
                   'message_id':mid,'user_id':user,'group_id':101,'raw_message':text,'font':0,
                   'sender':{'user_id':user,'nickname':f'Synthetic{user}','role':'member'},'message':parts}
            await ws.send(json.dumps(event,ensure_ascii=False))
            reply=await asyncio.wait_for(queue.get(),60)
            output=''.join(s.get('data',{}).get('text','') for s in reply.get('params',{}).get('message',[]))
            print(f'{mid}: {output}',flush=True)
            return output
        await turn(201,1,'请调用记忆工具，记住我喜欢喝枇杷乌龙。',True)
        reset=await turn(201,2,'/reset')
        assert 'cleared' in reset.lower() or '清空' in reset, 'context reset failed; privacy test would be invalid'
        before=await turn(202,3,'调用 find_shared_group_profile 查询群友 201 喜欢什么，没有授权就直接说不知道。',True)
        assert '枇杷乌龙' not in before
        assert '已允许' in await turn(201,4,'/共享我的画像')
        after=await turn(202,5,'请调用 find_shared_group_profile 查询群友 201 的画像，他喜欢喝什么？',True)
        assert '枇杷乌龙' in after
        assert '已关闭' in await turn(201,6,'/关闭画像共享')
        reader.cancel()

asyncio.run(main())
