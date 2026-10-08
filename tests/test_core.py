import unittest, tempfile, pathlib, importlib.util, sys, io, json, os
from unittest.mock import patch,Mock
ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import common

def module(path):
 spec=importlib.util.spec_from_file_location(path.replace('/','_'),ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Core(unittest.TestCase):
 def test_env_comments_quotes_precedence(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'env';p.write_text('A="hello world" # comment\nB=\nMACHINE_NAME=fixture\n')
   with patch.dict(os.environ,{'A':'override'}):cfg=common.load_env(str(p))
   self.assertEqual(cfg['A'],'override');self.assertEqual(cfg['B'],'')
 def test_identity_and_bind_fail_closed(self):
  with patch('common.subprocess.run',return_value=Mock(stdout='100.64.0.2\n')):
   self.assertEqual(common.tailscale_ip(),'100.64.0.2')
   with self.assertRaises(ValueError):common.tailscale_ip('0.0.0.0')
  with patch('common.subprocess.run',return_value=Mock(stdout=json.dumps({'UserProfile':{'LoginName':'owner@example.test'}}))):
   self.assertTrue(common.authorized('100.64.0.1','owner@example.test'))
   self.assertFalse(common.authorized('100.64.0.1','other@example.test'))
   self.assertFalse(common.authorized('192.168.1.2','owner@example.test'))
   self.assertFalse(common.authorized('100.64.0.1',''))
 def test_pagination_with_smaller_server_cap(self):
  source=list(range(1201))
  def get(path):offset=int(path.split('offset=')[1]);return source[offset:offset+100]
  self.assertEqual(common.pages(get,'metrics?order=ts.asc'),source)
 def test_new_and_legacy_supabase_headers(self):
  for key in ["sb_publishable_fixture","sb_secret_fixture"]:
   self.assertEqual(common.supabase_headers(key)["apikey"],key)
   self.assertNotIn("Authorization",common.supabase_headers(key))
  self.assertEqual(common.supabase_headers("legacy.jwt.fixture")["Authorization"],"Bearer legacy.jwt.fixture")
 def test_scoped_transport_never_uses_service_key(self):
  cfg={'SUPABASE_URL':'https://fixture.supabase.co','SUPABASE_ANON_KEY':'anon','AGENT_TOKEN':'token','MACHINE_NAME':'fixture','SUPABASE_SERVICE_KEY':'must-not-use'}
  with patch('common.urllib.request.urlopen') as send:
   common.scoped_request(cfg,'metrics','POST',{'machine':'other','cpu':2})
   request=send.call_args.args[0];body=json.loads(request.data)
   self.assertEqual(body['p_machine'],'fixture');self.assertEqual(request.headers['Authorization'],'Bearer anon')
   self.assertNotIn('must-not-use',request.data.decode())
 def test_runner_dryrun_has_no_writes(self):
  runner=module('actions/action-runner.py');calls=[]
  def fake(path,method='GET',body=None):calls.append(method);return [{'power_profile':'balanced'}] if method=='GET' else []
  with patch.object(runner,'SUPA_URL','mock'),patch.object(runner,'SUPA_KEY','mock'),patch.object(runner,'_supa',side_effect=fake),patch.object(runner,'audit'):
   runner.check_app_actions(True)
  self.assertEqual(calls,['GET'])
 def test_once_failure_is_nonzero(self):
  for path in ['agent/agent.py','windows/agent_windows.py']:
   with patch.dict(os.environ,{'MACHINE_NAME':'fixture'}):agent=module(path)
   with patch.object(agent,'SUPABASE_URL','mock'),patch.object(agent,'SERVICE_KEY','mock'),patch.object(agent,'one_cycle',return_value=False),patch.object(sys,'argv',['agent','--once']):
    with self.assertRaises(SystemExit) as error:agent.main()
    self.assertEqual(error.exception.code,1)
 def test_live_includes_timestamp(self):
  with patch.dict(os.environ,{'MACHINE_NAME':'fixture'}):agent=module('agent/agent.py')
  row=agent.collect_live();self.assertIn('ts',row);self.assertTrue(row['ts'].endswith('+00:00'))
 def test_render_png_and_escape(self):
  renderer=module('render/render.py');png=renderer.render_png(renderer.DEMO)
  self.assertTrue(png.startswith(b'\x89PNG'));self.assertIn('&lt;script&gt;',renderer.build_svg({'title':'Test','rows':[{'label':'TEST','value':'<script>'}]}))
 def test_overview_stale_and_injection(self):
  template=module('overview/overview-template.py')
  stale=template.build_html_single({'machine':'fixture','ts':'2000-01-01T00:00:00Z'},'<script>bad()</script>','test')
  self.assertNotIn('<script>bad()',stale);self.assertIn('offline',stale)
  row={'machine':'fixture','ts':common.utcnow(),'cpu':10,'mem':20,'disk':30,'_peak':{'culprit':'<script>bad()</script>'},'hardware':{'cpu':'<b>CPU</b>'}}
  html=template.build_html_single(row,'<script>bad()</script>','test');self.assertNotIn('<script>bad()',html);self.assertIn('&lt;b&gt;CPU',html)
 def test_updater_preserves_external_holds(self):
  updater=module('updater/update.py');remove,add,owned=updater.reconcile({'external','owned'},{'owned'},{'new'})
  self.assertEqual(remove,{'owned'});self.assertEqual(add,{'new'});self.assertEqual(owned,{'new'})
 def test_updater_network_failure_runs_no_commands(self):
  updater=module('updater/update.py');run=Mock()
  with patch.object(updater,'scoped_request',side_effect=OSError('offline')):
   with self.assertRaises(OSError):updater.perform({},run=run)
  run.assert_not_called()
 def test_update_failure_does_not_notify_success(self):
  updater=module('updater/update.py');response=Mock();response.__enter__=Mock(return_value=io.BytesIO(b'[]'));response.__exit__=Mock(return_value=False)
  def run(cmd):
   if 'upgrade' in cmd:raise RuntimeError('apt failed')
   return 'external' if 'showhold' in cmd else ''
  with tempfile.TemporaryDirectory() as d,patch.object(updater,'scoped_request',return_value=response),patch.object(updater,'notify') as notify:
   with self.assertRaises(RuntimeError):updater.perform({},pathlib.Path(d)/'holds.json',run)
   notify.assert_not_called()
 def test_installer_config(self):
  installer=module('install/setup.py');cfg={'SUPABASE_URL':'https://fixture.supabase.co','MACHINE_NAME':'fixture','SUPABASE_ANON_KEY':'anon','SUPABASE_SERVICE_KEY':'svc','SYSDASH_ROLE':'hub','INSTALL_MODE':'basis','SYSDASH_OPERATORS':'owner','HUB_URL':'http://100.64.0.2:9000'}
  installer.validate(cfg)
  with self.assertRaises(ValueError):installer.validate({**cfg,'ENABLE_UPDATES':'true'})
if __name__=='__main__':unittest.main()
