"""Real local HTTP requests; identity and database transport are isolated fixtures."""
import threading, unittest, urllib.request, urllib.error, json, io
from unittest.mock import patch, Mock
from http.server import ThreadingHTTPServer
from test_core import module

class Http(unittest.TestCase):
 def request(self,server,path,body=None,headers=None,method=None):
  req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {},method=method)
  try:
   with urllib.request.urlopen(req,timeout=3) as r:return r.status,r.read()
  except urllib.error.HTTPError as e:return e.code,e.read()
 def server(self,handler):
  server=ThreadingHTTPServer(('127.0.0.1',0),handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  return server
 def test_private_dashboard_config_and_read_only_proxy(self):
  web=module('web/server.py');server=self.server(web.Handler)
  cfg={'HUB_URL':'http://100.64.0.2:9000','SUPABASE_URL':'https://fixture.supabase.co','SUPABASE_SERVICE_KEY':'sb_secret_never_in_browser','SYSDASH_OPERATORS':'fixture'}
  with patch.object(web,'CFG',cfg),patch.object(web,'authorized',return_value=False):
   self.assertEqual(self.request(server,'/config.js')[0],403)
   self.assertEqual(self.request(server,'/',method='HEAD')[0],403)
  response=Mock();response.__enter__=Mock(return_value=io.BytesIO(b'[]'));response.__exit__=Mock(return_value=False)
  original=urllib.request.urlopen
  def transport(req,*args,**kwargs):
   if req.full_url.startswith('https://fixture.supabase.co'):
    self.assertEqual(req.headers['Apikey'],'sb_secret_never_in_browser');self.assertNotIn('Authorization',req.headers)
    return response
   return original(req,*args,**kwargs)
  with patch.object(web,'CFG',cfg),patch.object(web,'authorized',return_value=True),patch.object(web.urllib.request,'urlopen',side_effect=transport):
   status,config=self.request(server,'/config.js');self.assertEqual(status,200);self.assertNotIn(b'sb_secret',config)
   self.assertEqual(self.request(server,'/api/metrics')[0],200)
   self.assertEqual(self.request(server,'/api/sysdash_agent_tokens')[0],400)
   self.assertEqual(self.request(server,'/api/metrics?unsupported=value')[0],400)
   self.assertEqual(self.request(server,'/api/metrics',{},method='POST')[0],501)
 def test_gateway_checks_identity_origin_machine_and_mode(self):
  gateway=module('actions/actions-gateway.py');server=self.server(gateway.Handler)
  payload={'machine':'fixture','service':'restart-agent'}
  with patch.object(gateway,'OPERATORS','fixture'),patch.object(gateway,'ORIGINS',{'http://hub.test'}),patch.object(gateway,'MACHINE','fixture'),patch.object(gateway,'INSTALL_MODE','advanced'),patch.object(gateway,'do_restart',return_value=(True,'fixture')) as action:
   with patch.object(gateway,'authorized',return_value=False):self.assertEqual(self.request(server,'/restart',payload)[0],403)
   with patch.object(gateway,'authorized',return_value=True):
    self.assertEqual(self.request(server,'/restart',payload,{'Origin':'http://evil.test'})[0],403)
    self.assertEqual(self.request(server,'/restart',{**payload,'machine':'wrong'})[0],400)
    with patch.object(gateway,'INSTALL_MODE','basis'),patch.object(gateway,'audit'):
     self.assertEqual(self.request(server,'/restart',payload)[0],403)
    action.assert_not_called()
    self.assertEqual(self.request(server,'/restart',payload,{'Origin':'http://hub.test'})[0],200)
    action.assert_called_once_with('restart-agent')
 def test_gateway_serializes_mutations(self):
  gateway=module('actions/actions-gateway.py');server=self.server(gateway.Handler)
  gateway.ACTION_LOCK.acquire()
  try:
   with patch.object(gateway,'authorized',return_value=True):self.assertEqual(self.request(server,'/reboot',{'machine':'fixture'})[0],409)
  finally:gateway.ACTION_LOCK.release()
