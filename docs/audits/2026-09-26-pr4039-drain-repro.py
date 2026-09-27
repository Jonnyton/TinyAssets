import asyncio, signal, socket, threading, time, json, contextlib, sys
import httpx, uvicorn, importlib.metadata
from fastmcp import FastMCP
from sse_starlette.sse import AppStatus
started = threading.Event()
finished = threading.Event()
m = FastMCP('drain-repro')
@m.tool()
def converse() -> str:
    started.set()
    time.sleep(2)
    finished.set()
    return 'TURN_FINISHED'
async def main():
    print({p:importlib.metadata.version(p) for p in ('uvicorn','fastmcp','mcp','sse-starlette')})
    sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen(); port=sock.getsockname()[1]
    app=m.http_app(path='/mcp',transport='streamable-http')
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=(.25 if '--short-timeout' in sys.argv else 5)))
    server.capture_signals = contextlib.nullcontext
    if '--disable-sse-exit' in sys.argv: AppStatus.disable_automatic_graceful_drain()
    task=asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started: await asyncio.sleep(.01)
    headers={'Accept':'application/json, text/event-stream'}
    async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',headers=headers,timeout=8) as client:
        init=await client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'review','version':'1'}}})
        client.headers['mcp-session-id']=init.headers['mcp-session-id']
        await client.post('/mcp',json={'jsonrpc':'2.0','method':'notifications/initialized'})
        call=asyncio.create_task(client.post('/mcp',json={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'converse','arguments':{}}}))
        while not started.is_set(): await asyncio.sleep(.01)
        t=time.monotonic(); server.handle_exit(signal.SIGTERM,None)
        try:
            result=await call
            print('HTTP ended after',round(time.monotonic()-t,3),'s; status',result.status_code,'body',repr(result.text),'tool_finished',finished.is_set())
        except Exception as e: print('HTTP error after',round(time.monotonic()-t,3),'s:',type(e).__name__,str(e),'tool_finished',finished.is_set())
        await asyncio.wait_for(task,8)
        print('server exited after',round(time.monotonic()-t,3),'s; tool_finished',finished.is_set())
asyncio.run(main())


