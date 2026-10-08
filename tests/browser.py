"""Headless real Chromium; all requests use fixtures, never real machines."""
import json,pathlib,datetime
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
NOW=datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for mode in ['basis','windows','advanced']:
   ctx=browser.new_context();page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   capabilities={'gateway':True,'profiles':True,'updates':True} if mode=='advanced' else {}
   machine={'machine':'fixture','label':'Fixture','role':'hub','capabilities':capabilities,'tailscale_ip':'100.64.0.2' if mode=='advanced' else None}
   def route(rt):
    url=rt.request.url
    if '/api/' in url:
     table=url.split('/api/')[1].split('?')[0];offset=0
     data={'machines':[machine],'v_latest':[{'machine':'fixture','ts':NOW,'cpu':5,'mem':30,'disk':40,'extra':{}}],'config':[{'thresholds':{'default':{}}}],'live':[{'machine':'fixture','ts':'2000-01-01T00:00:00Z','cpu':99}],'metrics':[],'update_holds':[],'machine_actions':[],'action_log':[]}.get(table,[])
     rt.fulfill(content_type='application/json',body=json.dumps(data));return
    if '100.64.0.2:7072/mode' in url:
     rt.fulfill(content_type='application/json',headers={'Access-Control-Allow-Origin':'http://sysdash.test'},body=json.dumps({'mode':'advanced','has_webhook':False}));return
    name=url.split('sysdash.test/')[-1].split('?')[0] or 'index.html'
    if name=='config.js':rt.fulfill(content_type='application/javascript',body='window.SYSDASH_CONFIG={apiBase:"/api",hub:"http://sysdash.test"};');return
    file=ROOT/'web'/name
    if file.is_file():rt.fulfill(content_type={'.js':'application/javascript','.css':'text/css','.html':'text/html','.png':'image/png','.jpg':'image/jpeg'}.get(file.suffix,'application/octet-stream'),body=file.read_bytes());return
    rt.fulfill(status=404,body='unknown fixture')
   page.route('**/*',route);page.goto('http://sysdash.test/');page.wait_for_selector('#rings .ring');page.wait_for_timeout(100)
   assert page.locator('#rebootbtn').count()==(1 if mode=='advanced' else 0),mode
   assert page.locator('#cleanupbtn').count()==(1 if mode=='advanced' else 0),mode
   assert page.locator('#upgradebtn').count()==0
   assert page.locator('#rings .rval').first.text_content()=='5'
   assert not errors,errors
   # All tabs render on a narrow mobile viewport too.
   page.set_viewport_size({'width':390,'height':844})
   for name in ['systeem','beheer','historie','overzicht']:
    page.locator(f'.stab[data-s="{name}"]').click();assert page.locator(f'.panel[data-panel="{name}"]').is_visible()
   print('Chromium '+mode+': OK; stale live ignored; supported controls only; mobile tabs work')
   ctx.close()
  browser.close()
if __name__=='__main__':main()
