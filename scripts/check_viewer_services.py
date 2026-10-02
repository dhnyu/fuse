#!/usr/bin/env python3
"""Check/recover the authorized loopback Hub and existing Quick Tunnel only."""
from pathlib import Path
import argparse,json,re,shlex,subprocess,sys,time
REPO=Path(__file__).resolve().parents[1]

def session(name):return subprocess.run(['tmux','has-session','-t',name],capture_output=True).returncode==0

def start(name,command,log):
 if session(name):raise RuntimeError(f'{name} exists but is not healthy; no process stopped')
 line=shlex.join(command)+' >> '+shlex.quote(str(log))+' 2>&1'
 subprocess.run(['tmux','new-session','-d','-s',name,'exec '+line],check=True)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
 checker=[sys.executable,str(REPO/'scripts/serve_viewer_hub_fast.py'),'--check']
 listener=subprocess.check_output(['ss','-H','-ltnp','sport = :8765'],text=True)
 if not listener.strip():
  if args.check_only:raise RuntimeError('Hub missing')
  start('viewer-hub',[sys.executable,'-u',str(REPO/'scripts/serve_viewer_hub_fast.py')],REPO/'logs/viewer_hub_fast.log')
  for _ in range(30):
   if subprocess.run(checker,capture_output=True).returncode==0:break
   time.sleep(.2)
 subprocess.run(checker,check=True)
 if not session('s10-viewer-share'):
  # A cloudflared outside this tmux may still be healthy: do not duplicate it.
  processes=subprocess.run(['pgrep','-a','-u',str(__import__('os').getuid()),'cloudflared'],capture_output=True,text=True).stdout
  if processes.strip():raise RuntimeError('Existing cloudflared outside expected session; no duplicate started')
  if args.check_only:raise RuntimeError('Tunnel missing')
  binary=Path.home()/'.local/bin/cloudflared'
  if not binary.is_file():raise RuntimeError('cloudflared missing; no automatic installation')
  start('s10-viewer-share',[str(binary),'tunnel','--no-autoupdate','--url','http://127.0.0.1:8765'],REPO/'logs/viewer_cloudflare_current.log')
  time.sleep(5)
 pids=subprocess.check_output(['tmux','list-panes','-t','s10-viewer-share','-F','#{pane_pid}'],text=True).split()
 if len(pids)!=1:raise RuntimeError('Ambiguous tunnel session')
 pid=int(pids[0]);proc=Path(f'/proc/{pid}');cmd=(proc/'cmdline').read_bytes().decode().split('\0')
 if not any(Path(x).name=='cloudflared' for x in cmd) or 'http://127.0.0.1:8765' not in cmd:raise RuntimeError('Unexpected tunnel command; no action taken')
 log=(proc/'fd/1').resolve()
 urls=re.findall(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com',log.read_text(errors='replace')) if log.is_file() else []
 print(json.dumps({'tunnel_pid':pid,'public_url':urls[-1] if urls else None,'log':str(log)}))
 if not urls:raise RuntimeError('Tunnel URL not yet available; inspect log, no restart performed')
if __name__=='__main__':
 try:main()
 except (RuntimeError,subprocess.CalledProcessError,OSError) as e:sys.exit(str(e))
