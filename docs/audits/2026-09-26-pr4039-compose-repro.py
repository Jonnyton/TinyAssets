import subprocess,tempfile,pathlib,json
for value in ['300s','5m0s','300.0s','300000ms','1h30m','300','"300"']:
    with tempfile.TemporaryDirectory(prefix='pr4039-compose-') as tmp:
        p=pathlib.Path(tmp)/'compose.yml';p.write_text('services:\n  daemon:\n    image: busybox\n    stop_grace_period: '+value+'\n')
        r=subprocess.run(['docker','compose','-f',str(p),'config','--format','json'],capture_output=True,text=True)
        result=json.loads(r.stdout)['services']['daemon']['stop_grace_period'] if r.returncode==0 else r.stderr.strip()
        print(value, '=>',r.returncode,result)
