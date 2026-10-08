#!/usr/bin/env python3
"""Guided installer for Debian/Ubuntu with systemd. Never source a user's .env as root."""
import argparse, getpass, os, re, sys, json, shlex, shutil, subprocess, secrets, hashlib, urllib.request
from pathlib import Path
SOURCE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(SOURCE))
from common import load_env, tailscale_ip, supabase_headers
DEST=Path('/opt/sysdash');CONFIG=Path('/etc/sysdash/sysdash.env')
UNITS=['sysdash-agent','sysdash-live','sysdash-web','sysdash-actions-gateway','sysdash-actions','sysdash-render','sysdash-overview.timer','sysdash-update.timer','sysdash-tunnel','sysdash-boot-notify','sysdash-update.service','sysdash-overview.service']
def run(args):subprocess.run(args,check=True)
def atomic(path,text,mode=0o640):
    tmp=path.with_suffix('.new');tmp.write_text(text);tmp.chmod(mode);os.replace(tmp,path)
def validate(cfg):
    if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co',cfg.get('SUPABASE_URL','')):raise ValueError('Vul de HTTPS Supabase-project-URL in')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',cfg.get('MACHINE_NAME','')):raise ValueError('Machinenaam: maximaal 64 kleine letters/cijfers/_/-')
    if not cfg.get('SUPABASE_ANON_KEY'):raise ValueError('Supabase anon-key ontbreekt')
    if cfg['SYSDASH_ROLE']=='hub' and not cfg.get('SUPABASE_SERVICE_KEY'):raise ValueError('Hub service-key ontbreekt')
    if cfg['SYSDASH_ROLE']=='agent' and len(cfg.get('AGENT_TOKEN',''))<32:raise ValueError('Eigen machine-token ontbreekt')
    if not cfg.get('SYSDASH_OPERATORS'):raise ValueError('Geef ten minste één toegestane Tailscale-login op')
    if cfg.get('ENABLE_UPDATES')=='true' and cfg.get('INSTALL_MODE')!='advanced':raise ValueError('Updates vereisen Advanced')
    if not re.fullmatch(r'http://100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}:9000',cfg.get('HUB_URL','')):raise ValueError('Hubadres moet http://<Tailscale-IP>:9000 zijn')
def prompt(cfg,key,label,secret=False,default=''):
    current=cfg.get(key,default)
    value=(getpass.getpass if secret else input)(label+(' [bestaande waarde behouden]' if current and secret else f' [{current}]' if current else '')+': ')
    cfg[key]=value.strip() or current

def main():
    parser=argparse.ArgumentParser(description='SysDash begeleide installatie')
    parser.add_argument('--role',choices=['hub','agent'],default='hub');parser.add_argument('--mode',choices=['basis','advanced'],default='basis')
    parser.add_argument('--config',type=Path);parser.add_argument('--check',action='store_true');parser.add_argument('--noninteractive',action='store_true');parser.add_argument('--enable-updates',action='store_true')
    args=parser.parse_args()
    cfg=load_env(str(args.config or CONFIG))
    # Keep only supported configuration; never persist arbitrary inherited environment.
    names=['SUPABASE_URL','SUPABASE_ANON_KEY','SUPABASE_SERVICE_KEY','MACHINE_NAME','AGENT_TOKEN','SYSDASH_OPERATORS','HUB_URL','DISCORD_WEBHOOK','HEALTHCHECK_PING_URL']
    cfg={k:cfg.get(k,'') for k in names};cfg.update(SYSDASH_ROLE=args.role,INSTALL_MODE=args.mode,ENABLE_UPDATES='true' if args.enable_updates else 'false')
    if not args.noninteractive and not args.check:
        print('SysDash — stap voor stap. Gebruik een apart Supabase-project met db/install.sql. Geheime waarden worden niet getoond.')
        for key,label,secret in [('SUPABASE_URL','Supabase project-URL',False),('SUPABASE_ANON_KEY','Supabase anon-key',True),('MACHINE_NAME','Unieke machinenaam',False),('SYSDASH_OPERATORS','Toegestane Tailscale-login(s), komma gescheiden',False)]:prompt(cfg,key,label,secret)
        if args.role=='hub':prompt(cfg,'SUPABASE_SERVICE_KEY','Supabase service-key, alleen op deze hub',True)
        else:prompt(cfg,'AGENT_TOKEN','Machine-token aangemaakt op de hub',True)
        if args.mode=='advanced':prompt(cfg,'DISCORD_WEBHOOK','Discord-webhook, optioneel',True)
    ip=tailscale_ip()
    if args.role=='hub':cfg['HUB_URL']=f'http://{ip}:9000'
    elif not args.noninteractive and not args.check:prompt(cfg,'HUB_URL','Dashboardadres van de hub')
    validate(cfg)
    print('Configuratie en Tailscale geldig; rol='+args.role+', modus='+args.mode+', updates='+cfg['ENABLE_UPDATES'])
    if args.check:return 0
    if os.geteuid()!=0:raise ValueError('Start met sudo bash install/setup.sh (de installer heeft systeemrechten nodig)')
    if args.role=='hub':
        cfg['AGENT_TOKEN']=cfg.get('AGENT_TOKEN') or secrets.token_urlsafe(32)
        service=cfg['SUPABASE_SERVICE_KEY']
        payload={'machine':cfg['MACHINE_NAME'],'token_hash':hashlib.sha256(cfg['AGENT_TOKEN'].encode()).hexdigest()}
        req=urllib.request.Request(cfg['SUPABASE_URL']+'/rest/v1/sysdash_agent_tokens?on_conflict=machine',data=json.dumps(payload).encode(),headers={**supabase_headers(service),'Prefer':'resolution=merge-duplicates'},method='POST')
        with urllib.request.urlopen(req,timeout=15):pass # verify schema BEFORE changing system
    else:
        from common import scoped_request
        with scoped_request(cfg,'machine_actions') as response:json.loads(response.read())
    if not shutil.which('systemctl') or not shutil.which('apt-get'):raise ValueError('Alleen Debian/Ubuntu met systemd wordt ondersteund')
    if subprocess.run(['systemctl','is-active','--quiet','sysdash-update.service']).returncode==0:raise ValueError('Er loopt een update. Wacht tot die voltooid is en start de installer opnieuw.')
    run(['apt-get','update']);run(['apt-get','install','-y','python3-venv','libcairo2','python3-dev','fonts-dejavu-core'])
    if not shutil.which('powerprofilesctl') and args.mode=='advanced':print('Geen powerprofilesctl: energieprofielknoppen blijven uit.')
    if subprocess.run(['id','sysdash'],capture_output=True).returncode:run(['useradd','--system','--home-dir','/var/lib/sysdash','--create-home','--shell','/usr/sbin/nologin','sysdash'])
    CONFIG.parent.mkdir(mode=0o750,exist_ok=True);shutil.chown(CONFIG.parent,user='root',group='sysdash');CONFIG.parent.chmod(0o750)
    DEST.mkdir(mode=0o755,exist_ok=True)
    for parent in [Path('/opt'),DEST,Path('/usr/local'),Path('/usr/local/libexec')]:
        if parent.exists() and (parent.is_symlink() or parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022):raise ValueError('Systeemmap niet beschermd: '+str(parent))
    if DEST.is_symlink():raise ValueError('Installatiemap mag geen symlink zijn')
    # Stop old units before replacing code. New config contains no sourced shell code.
    for unit in UNITS:subprocess.run(['systemctl','disable','--now',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for name in ['agent','actions','web','render','overview','updater','boot-notify','tunnel','common.py','requirements.txt']:
        source=SOURCE/name;target=DEST/name
        if source.resolve()==target.resolve():continue
        if source.is_dir():
            if target.exists():shutil.rmtree(target)
            shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.log','.env'))
        else:shutil.copy2(source,target)
    for name in ['agent','actions','web','render','overview','updater','boot-notify','tunnel','common.py','requirements.txt']:
        target=DEST/name
        paths=[target,*target.rglob('*')] if target.is_dir() else [target]
        for path in paths:
            if path.is_symlink():raise ValueError('Geen symlinks in installatiebronnen toegestaan')
            shutil.chown(path,user='root',group='root')
            path.chmod(0o755 if path.is_dir() else 0o644)
    if (DEST/'.venv').is_symlink():raise ValueError('Virtualenv mag geen symlink zijn')
    if (DEST/'.venv').exists():shutil.rmtree(DEST/'.venv')
    run(['python3','-m','venv',str(DEST/'.venv')]);run([str(DEST/'.venv/bin/pip'),'install','-r',str(DEST/'requirements.txt')])
    cfg['SYSDASH_ORIGINS']=cfg['HUB_URL'];cfg['SYSDASH_ENV']=str(CONFIG);cfg['AUDIT_PATH']='/var/lib/sysdash/audit.log'
    cfg['HAS_PROFILES']='true' if shutil.which('powerprofilesctl') else 'false'
    cfg['PLAYWRIGHT_BROWSERS_PATH']='/opt/sysdash/browsers'
    if args.role=='hub' and args.mode=='advanced':
        run([str(DEST/'.venv/bin/python'),'-m','playwright','install-deps','chromium'])
        env=dict(os.environ,PLAYWRIGHT_BROWSERS_PATH=cfg['PLAYWRIGHT_BROWSERS_PATH'])
        subprocess.run([str(DEST/'.venv/bin/python'),'-m','playwright','install','chromium'],env=env,check=True)
    atomic(CONFIG,''.join(k+'='+shlex.quote(str(v))+'\n' for k,v in cfg.items()));shutil.chown(CONFIG,user='root',group='sysdash')
    Path('/var/lib/sysdash').mkdir(exist_ok=True);shutil.chown('/var/lib/sysdash',user='sysdash',group='sysdash')
    Path('/var/lib/sysdash-updater').mkdir(mode=0o700,exist_ok=True)
    shutil.chown('/var/lib/sysdash-updater',user='root',group='root');Path('/var/lib/sysdash-updater').chmod(0o700)
    helper=Path('/usr/local/libexec/sysdash-action');helper.parent.mkdir(parents=True,exist_ok=True)
    atomic(helper,'#!/bin/sh\nexec /usr/bin/python3 -I /opt/sysdash/actions/privileged.py "$@"\n',0o755)
    sudoers=Path('/etc/sudoers.d/sysdash');text=(SOURCE/'actions'/('sudoers.example' if args.mode=='advanced' else 'sudoers-basis.example')).read_text().replace('__USER__','sysdash')
    tmp=sudoers.with_suffix('.new');atomic(tmp,text,0o440);run(['visudo','-cf',str(tmp)]);os.replace(tmp,sudoers)
    def unit(name,execstart,root=False,timer=False):
        text=f'[Unit]\nDescription=SysDash {name}\nAfter=network-online.target tailscaled.service\nWants=network-online.target\n[Service]\nUser={"root" if root else "sysdash"}\nWorkingDirectory=/opt/sysdash\nEnvironmentFile={CONFIG}\nExecStart={execstart}\n'
        text+='Type=oneshot\n' if timer else 'Restart=on-failure\nRestartSec=10\n'
        text+='ProtectSystem=strict\nReadWritePaths=/var/lib/sysdash /var/lib/sysdash-updater /run/lock /tmp\n' if not root and name not in ['actions','actions-gateway'] else ''
        text+='[Install]\nWantedBy=multi-user.target\n'
        atomic(Path('/etc/systemd/system/sysdash-'+name+'.service'),text,0o644)
    py='/opt/sysdash/.venv/bin/python'
    unit('agent',py+' /opt/sysdash/agent/agent.py');unit('live',py+' /opt/sysdash/agent/agent.py --live')
    enabled=['sysdash-agent','sysdash-live']
    if args.role=='hub':unit('web',py+' /opt/sysdash/web/server.py');enabled.append('sysdash-web')
    if args.mode=='advanced':
        unit('actions-gateway',py+' /opt/sysdash/actions/actions-gateway.py');unit('actions',py+' /opt/sysdash/actions/action-runner.py');enabled+=['sysdash-actions','sysdash-actions-gateway']
        if args.role=='hub':
            unit('render',py+' /opt/sysdash/render/render.py');enabled.append('sysdash-render');unit('overview',py+' /opt/sysdash/overview/sysdash-overview.py',timer=True)
            shutil.copy2(SOURCE/'overview/sysdash-overview.timer','/etc/systemd/system/sysdash-overview.timer');enabled.append('sysdash-overview.timer')
        if args.enable_updates:
            unit('update',py+' /opt/sysdash/updater/update.py',root=True,timer=True);shutil.copy2(SOURCE/'updater/sysdash-update.timer','/etc/systemd/system/sysdash-update.timer');enabled.append('sysdash-update.timer')
    run(['systemctl','daemon-reload']);run(['systemctl','enable','--now',*enabled])
    # A service being active isn't proof of successful ingestion.
    env=dict(os.environ,**cfg)
    subprocess.run([py,str(DEST/'agent/agent.py'),'--once'],env=env,check=True,timeout=180)
    for name in enabled:run(['systemctl','is-active','--quiet',name])
    print('Installatie gecontroleerd: eerste meting ontvangen en diensten actief. Dashboard: '+cfg['HUB_URL'])
    return 0
if __name__=='__main__':
    try:sys.exit(main())
    except ValueError as e:print('Installatie gestopt: '+str(e),file=sys.stderr);sys.exit(1)
    except Exception as e:print('Installatie gestopt: '+type(e).__name__+'. Controleer configuratie, netwerk en bovenstaande stap. Geen succes bevestigd.',file=sys.stderr);sys.exit(1)
