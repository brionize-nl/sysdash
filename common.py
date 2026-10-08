"""Shared config, REST pagination and Tailscale identity checks."""
import os, json, shlex, subprocess, ipaddress, urllib.request, urllib.parse

def load_env(path=None):
    cfg = {}
    path = path or os.environ.get('SYSDASH_ENV', '/etc/sysdash/sysdash.env')
    if not os.path.isfile(path): path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.isfile(path):
        with open(path, encoding='utf-8-sig') as stream:
            for line in stream:
                line = line.strip()
                if not line or line.startswith('#'): continue
                key, sep, value = line.partition('=')
                if sep:
                    values = shlex.split(value, comments=True, posix=True)
                    cfg[key.strip()] = ' '.join(values)
    cfg.update(os.environ)
    return cfg

def utcnow():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def tailscale_ip(override=None):
    value = subprocess.run(['tailscale', 'ip', '-4'], check=True, capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
    ip = ipaddress.ip_address(value)
    if ip not in ipaddress.ip_network('100.64.0.0/10'): raise ValueError('Geen Tailscale IPv4-adres')
    if override and override != value: raise ValueError('Bindadres moet het echte Tailscale-adres zijn')
    return value

def authorized(address, operators):
    if not operators: return False
    try:
        ip = ipaddress.ip_address(address)
        if ip not in ipaddress.ip_network('100.64.0.0/10'): return False
        result = subprocess.run(['tailscale','whois','--json',address], check=True, capture_output=True, text=True, timeout=5)
        identity = json.loads(result.stdout).get('UserProfile', {}).get('LoginName', '')
        return identity.casefold() in {x.strip().casefold() for x in operators.split(',') if x.strip()}
    except (ValueError, OSError, subprocess.SubprocessError): return False

def pages(get, path, size=500):
    rows=[]; offset=0
    while True:
        batch=get(path + ('&' if '?' in path else '?') + f'limit={size}&offset={offset}')
        rows.extend(batch)
        if not batch: break
        offset += len(batch)
        # Continue even if a server's row cap is smaller than the requested page size.
    return rows

def supabase_headers(key):
    # New publishable/secret keys are not JWTs; passing them as Bearer is rejected.
    headers={'apikey':key,'Content-Type':'application/json'}
    if not key.startswith(('sb_publishable_','sb_secret_')):headers['Authorization']='Bearer '+key
    return headers

def scoped_request(cfg, path, method='GET', body=None):
    """Machine token can only access the machine-scoped RPC; no project service key."""
    table, _, query = path.partition('?')
    params = urllib.parse.parse_qs(query)
    action = {('machines','POST'):'register', ('machines','PATCH'):'hardware',
              ('metrics','POST'):'metrics', ('metrics','GET'):'history',
              ('live','POST'):'live', ('machine_actions','GET'):'profile-read',
              ('machine_actions','POST'):'profile-write', ('machine_actions','PATCH'):'profile-write',
              ('update_holds','GET'):'holds-read', ('update_holds','POST'):'hold-write',
              ('update_holds','DELETE'):'hold-delete', ('action_log','POST'):'log'}.get((table,method))
    if not action: raise ValueError('Unsupported agent operation')
    payload = dict(body or {})
    if action == 'history': payload['before'] = params.get('ts',[''])[0].removeprefix('lte.')
    if action == 'hold-delete': payload['package'] = params.get('package',[''])[0].removeprefix('eq.')
    url = cfg['SUPABASE_URL'].rstrip('/') + '/rest/v1/rpc/sysdash_agent_api'
    anon = cfg['SUPABASE_ANON_KEY']
    req = urllib.request.Request(url, data=json.dumps({'p_machine':cfg['MACHINE_NAME'], 'p_token':cfg['AGENT_TOKEN'], 'p_action':action, 'p_body':payload}).encode(), headers=supabase_headers(anon), method='POST')
    return urllib.request.urlopen(req,timeout=15)
