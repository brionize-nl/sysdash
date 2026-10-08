#!/usr/bin/env python3
"""Opt-in system updates: fail closed and preserve non-SysDash apt holds."""
import os, sys, json, re, subprocess, urllib.request, fcntl, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from common import load_env, scoped_request
PACKAGE=re.compile(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?')
def reconcile(current, owned, requested):
    """Return only our removals and newly owned additions; external holds stay untouched."""
    removals=owned-requested
    additions=requested-current
    return removals, additions, (owned-removals)|additions

def command(args):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=1800).stdout

def notify(cfg,message):
    hook=cfg.get('DISCORD_WEBHOOK','')
    if not hook:return
    if not re.fullmatch(r'https://discord.com/api/webhooks/\d+/[\w-]+',hook):raise ValueError('Ongeldige webhook')
    req=urllib.request.Request(hook,data=json.dumps({'username':'SysDash','content':message}).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=15):pass

def perform(cfg,state=Path('/var/lib/sysdash-updater/holds.json'),run=command):
    with scoped_request(cfg,'update_holds') as response: rows=json.loads(response.read())
    if not isinstance(rows,list):raise ValueError('Ongeldige blokkeerlijst')
    names=[]
    for row in rows:
        name=row.get('package') if isinstance(row,dict) else None
        if not isinstance(name,str) or not re.fullmatch(r'(?:flatpak:)?[A-Za-z0-9][A-Za-z0-9.+:_-]{0,199}',name):raise ValueError('Ongeldig pakket in blokkeerlijst')
        names.append(name)
    requested={n for n in names if not n.startswith('flatpak:')}
    if not all(PACKAGE.fullmatch(n) for n in requested):raise ValueError('Ongeldige apt-pakketnaam')
    stored=json.loads(state.read_text()) if state.exists() else []
    if not isinstance(stored,list) or not all(isinstance(n,str) and PACKAGE.fullmatch(n) for n in stored):raise ValueError('Ongeldige lokale holdadministratie')
    current=set(run(['/usr/bin/apt-mark','showhold']).split())
    owned=set(stored)
    remove,add,new_owned=reconcile(current,owned,requested)
    # Write ownership after every successful operation; interruption remains recoverable.
    def save():
        tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(sorted(owned)));os.chmod(tmp,0o600);os.replace(tmp,state)
    for name in sorted(remove):run(['/usr/bin/apt-mark','unhold',name]);owned.discard(name);save()
    for name in sorted(add):run(['/usr/bin/apt-mark','hold',name]);owned.add(name);save()
    run(['/usr/bin/apt-get','update'])
    run(['/usr/bin/apt-get','upgrade','-y','-o','Dpkg::Options::=--force-confdef','-o','Dpkg::Options::=--force-confold'])
    flatpak='/usr/bin/flatpak'
    if Path(flatpak).exists():
        for app in run([flatpak,'remote-ls','--system','--updates','--columns=application']).splitlines():
            app=app.strip()
            if not app or app.lower()=='application':continue
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]+',app):raise ValueError('Ongeldige Flatpak-ID')
            if 'flatpak:'+app not in names:run([flatpak,'update','--system','-y',app])
    notify(cfg,f"[OK] Update-run {cfg['MACHINE_NAME']} voltooid. Blokkades behouden; herstart nodig: {'ja' if Path('/var/run/reboot-required').exists() else 'nee'}.")

def main():
    cfg=load_env()
    if cfg.get('ENABLE_UPDATES')!='true':print('Automatische updates zijn niet ingeschakeld.');return 0
    if os.geteuid()!=0:return 2
    with open('/var/lib/sysdash-updater/packages.lock','a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 75
        try:perform(cfg)
        except Exception as error:
            # Never print an exception containing the webhook/token URL.
            print('Update-run mislukt: '+type(error).__name__,file=sys.stderr)
            try:notify(cfg,f"[FOUT] Update-run {cfg.get('MACHINE_NAME','')} mislukt. Bekijk het lokale servicelog; geen succes bevestigd.")
            except Exception:print('Ook foutmelding kon niet worden bezorgd',file=sys.stderr)
            return 1
    return 0
if __name__=='__main__':sys.exit(main())
