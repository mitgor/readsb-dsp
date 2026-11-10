#!/usr/bin/env python3
"""Install a dedicated source bundle and inactive systemd units on Debian Linux."""
import argparse, json, math, os, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path('/opt/readsb-dsp')

def units(lat, lon, gain):
    if not all(math.isfinite(v) for v in (lat, lon, gain)) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 0 <= gain <= 50:
        raise ValueError('Supply a valid latitude, longitude and tuner gain (0..50 dB)')
    common = '''[Unit]\nDescription=readsb-dsp {description}\nAfter=network.target\n[Service]\nUser=readsb-dsp\nGroup=readsb-dsp\nSupplementaryGroups=plugdev\nWorkingDirectory=/opt/readsb-dsp\nEnvironment=PYTHONPATH=/opt/readsb-dsp/src\nEnvironment=OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1\nRuntimeDirectory=readsb-dsp\nRuntimeDirectoryPreserve=yes\nStateDirectory=readsb-dsp\nExecStart={command}\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=true\n[Install]\nWantedBy=multi-user.target\n'''
    py = '/opt/readsb-dsp/.venv/bin/python'
    commands = {
      'receiver': f'/opt/readsb-dsp/readsb/readsb --device-type rtlsdr --device 0 --gain {gain} --lat {lat} --lon {lon} --net --net-bo-port 30005 --write-json /run/readsb-dsp',
      'decoder': f'{py} -m rescue.async_shadow --root /opt/readsb-dsp --runtime /run/readsb-dsp --readsb-json /run/readsb-dsp --archive /var/lib/readsb-dsp --lat {lat} --lon {lon} --config /etc/readsb-dsp/methods.json --worker-config /etc/readsb-dsp/workers.json --cpu-budget-config /etc/readsb-dsp/cpu-budget.json --no-logging',
      'relay': f'{py} -m rescue.async_feed --runtime /run/readsb-dsp --config /etc/readsb-dsp/methods.json --worker-config /etc/readsb-dsp/workers.json --port 31005',
      'dashboard': f'{py} -m deadsb.cli dashboard --runtime /run/readsb-dsp --budget-config /etc/readsb-dsp/cpu-budget.json',
    }
    result = {}
    for name, command in commands.items():
        text = common.format(description=name, command=command)
        if name == 'receiver':
            text = text.replace('[Service]', '[Service]\nEnvironment=ADSB_RESCUE_SOCKET=/run/readsb-dsp/iq.sock')
        result[f'readsb-dsp-{name}.service'] = text
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lat',required=True,type=float);p.add_argument('--lon',required=True,type=float)
    p.add_argument('--gain',required=True,type=float)
    p.add_argument('--render-only',type=Path,help='Generate service files only; no build/install/service changes')
    a=p.parse_args(); rendered=units(a.lat,a.lon,a.gain)
    if a.render_only:
        a.render_only.mkdir(parents=True,exist_ok=True)
        for name, data in rendered.items():(a.render_only/name).write_text(data)
        return
    if sys.platform!='linux' or os.geteuid()!=0:p.error('Run with sudo on Debian/Raspberry Pi OS, or use --render-only')
    if PREFIX.exists() or Path('/etc/readsb-dsp').exists() or any((Path('/etc/systemd/system')/n).exists() for n in rendered):
        p.error('Existing installation found. Refusing to overwrite it; use a reviewed migration.')
    subprocess.run(['git','-c',f'safe.directory={ROOT}','diff','--exit-code','HEAD'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    # Export only versioned source, never private RF, build products or credentials.
    PREFIX.mkdir()
    try:
        names=subprocess.check_output(['git','-c',f'safe.directory={ROOT}','ls-files','-z'],cwd=ROOT).decode().split('\0')
        for name in filter(None,names):
            if Path(name).parts[0] not in {'packaging','src','readsb','models','config','tools','docs','dashboard','pyproject.toml','README.md','LICENSE','COPYING','bundle-manifest.json'}:continue
            source=ROOT/name; dest=PREFIX/name
            if source.is_symlink():raise ValueError(f'Symlink in source: {name}')
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        subprocess.run(['python3','-m','venv',str(PREFIX/'.venv')],check=True)
        python=str(PREFIX/'.venv/bin/python')
        subprocess.run([python,'-m','pip','install','-e',str(PREFIX)],check=True)
        subprocess.run([python,str(PREFIX/'tools/build_bundle.py'),'--rtlsdr'],check=True)
        subprocess.run([python,'-c','from rescue.model_cascade import production_paths; production_paths("/opt/readsb-dsp")'],check=True)
        if subprocess.run(['id','readsb-dsp'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['useradd','--system','--user-group','--home-dir',str(PREFIX),'--no-create-home','--shell','/usr/sbin/nologin','--groups','plugdev','readsb-dsp'],check=True)
        cfg=Path('/etc/readsb-dsp');cfg.mkdir()
        for name in ('methods.json','workers.json','cpu-budget.json'):
            shutil.copy2(PREFIX/'config'/name,cfg/name)
            shutil.chown(cfg/name,user='readsb-dsp',group='readsb-dsp')
        shutil.chown(cfg,user='readsb-dsp',group='readsb-dsp')
        for name,data in rendered.items():(Path('/etc/systemd/system')/name).write_text(data)
        subprocess.run(['systemctl','daemon-reload'],check=True)
    except Exception:
        print('Installation incomplete; nothing was started. Inspect /opt/readsb-dsp before retrying.',file=sys.stderr)
        raise
    print('Installed. No services started and no feeders changed. Follow docs/INSTALL.md for activation.')
if __name__=='__main__':main()
