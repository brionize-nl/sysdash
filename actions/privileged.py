#!/usr/bin/env python3
"""Root-owned fixed action helper. No shell, paths or caller-supplied commands."""
import os, sys, subprocess, fcntl
ACTIONS={f'restart-{name}':['systemctl','restart',f'sysdash-{name}'] for name in ('render','agent','web','live','tunnel')}
ACTIONS['reboot']=['systemctl','reboot']
for profile in ('power-saver','balanced','performance'):ACTIONS['profile-'+profile]=['powerprofilesctl','set',profile]
def main():
    if os.geteuid()!=0 or len(sys.argv)!=2: return 2
    action=sys.argv[1]
    if action not in ACTIONS and action!='cleanup-safe': return 2
    with open('/var/lib/sysdash-updater/packages.lock','a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: print('Een andere systeemactie loopt nog',file=sys.stderr);return 75
        commands=[['apt-get','clean'],['journalctl','--vacuum-time=7d']] if action=='cleanup-safe' else [ACTIONS[action]]
        for command in commands:
            executable='/usr/bin/'+command[0]
            result=subprocess.run([executable,*command[1:]],timeout=180)
            if result.returncode:return result.returncode
    return 0
if __name__=='__main__': sys.exit(main())
