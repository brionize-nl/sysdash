#!/usr/bin/env python3
"""Tailscale identity-gated static dashboard and read-only Supabase proxy."""
import os, sys, json, urllib.request, urllib.parse
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from common import load_env, tailscale_ip, authorized, supabase_headers
CFG=load_env()
TABLES={'machines','v_latest','config','metrics','live','machine_actions','update_holds','action_log','baselines'}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(Path(__file__).parent),**kwargs)
    def do_HEAD(self):
        if not authorized(self.client_address[0],CFG.get("SYSDASH_OPERATORS","")):self.send_error(403);return
        super().do_HEAD()

    def do_GET(self):
        if not authorized(self.client_address[0],CFG.get('SYSDASH_OPERATORS','')):
            self.send_error(403,'Alleen toegestane Tailscale-gebruikers');return
        if self.path.startswith('/api/'):
            parsed=urllib.parse.urlsplit(self.path[5:]);table=parsed.path
            if table not in TABLES or len(self.path)>4096:self.send_error(400);return
            params=urllib.parse.parse_qs(parsed.query)
            if any(k not in {'select','order','limit','offset','machine','ts','cpu','freq'} for k in params):self.send_error(400);return
            try:
                key=CFG['SUPABASE_SERVICE_KEY']
                req=urllib.request.Request(CFG['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+self.path[5:],headers=supabase_headers(key))
                with urllib.request.urlopen(req,timeout=15) as response:body=response.read()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
            except Exception:self.send_error(502,'Database niet bereikbaar')
            return
        if self.path.split('?')[0]=='/config.js':
            body=('window.SYSDASH_CONFIG='+json.dumps({'apiBase':'/api','hub':CFG['HUB_URL']})+';').encode()
            self.send_response(200);self.send_header('Content-Type','application/javascript');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body);return
        super().do_GET()
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' http:")
        super().end_headers()
    def log_message(self,*args):pass
if __name__=='__main__':ThreadingHTTPServer((tailscale_ip(),9000),Handler).serve_forever()
