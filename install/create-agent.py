#!/usr/bin/env python3
"""Run locally on the hub as an administrator; write a per-machine token to a private file."""
import sys,os,json,secrets,hashlib,urllib.request,re,shlex
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from common import load_env, supabase_headers
if len(sys.argv)!=3 or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',sys.argv[1]):sys.exit('Gebruik: create-agent.py machinenaam nieuw-configbestand')
cfg=load_env();token=secrets.token_urlsafe(32);machine=sys.argv[1];key=cfg['SUPABASE_SERVICE_KEY']
# Never overwrite an existing config or silently rotate an existing token.
req=urllib.request.Request(cfg['SUPABASE_URL']+'/rest/v1/sysdash_agent_tokens',data=json.dumps({'machine':machine,'token_hash':hashlib.sha256(token.encode()).hexdigest()}).encode(),headers=supabase_headers(key),method='POST')
fd=os.open(sys.argv[2],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
try:
 with urllib.request.urlopen(req,timeout=15):pass
 with os.fdopen(fd,'w') as out:
  fd=None
  for k,v in {'MACHINE_NAME':machine,'AGENT_TOKEN':token,**{k:cfg[k] for k in ['SUPABASE_URL','SUPABASE_ANON_KEY','HUB_URL','SYSDASH_OPERATORS']}}.items():out.write(k+'='+shlex.quote(v)+'\n')
except Exception:
 if fd is not None:os.close(fd)
 Path(sys.argv[2]).unlink(missing_ok=True);raise
print('Machineconfig aangemaakt. Verstuur dit bestand uitsluitend via een privéverbinding; de inhoud is niet afgedrukt.')
