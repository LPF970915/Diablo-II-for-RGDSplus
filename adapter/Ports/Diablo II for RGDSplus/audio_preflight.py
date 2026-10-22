import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


SERVER = 'unix:/tmp/pulse-socket'


def pulse(*arguments, check=True):
    return subprocess.run(['pactl','-s',SERVER,*arguments],capture_output=True,text=True,check=check,timeout=8)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore-pending',action='store_true')
    parser.add_argument('--qa-mute',action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    pending = root/'audio-before-full-qa.json'
    report = {'server':SERVER,'serverStarted':False,'savedMixerSwitchesRestored':False}
    if pulse('info',check=False).returncode:
        subprocess.run(['/etc/init.d/S50pulseaudio','start'],check=True,timeout=15)
        for attempt in range(10):
            if pulse('info',check=False).returncode == 0:
                break
            time.sleep(.2)
        else:
            environment = dict(os.environ,PULSE_HOME='/tmp/.pulse')
            for name in ('ALSA_CONFIG_PATH','LD_PRELOAD','LD_LIBRARY_PATH'):
                environment.pop(name,None)
            subprocess.run(['/usr/bin/pulseaudio','-n','--file='+str(root/'audio-session.pa'),
                            '--daemonize','--exit-idle-time=-1','--log-target=file:'+str(root/'audio-daemon.log')],
                           env=environment,check=True,timeout=15)
            pulse('info')
            report['explicitHardwareFallback'] = True
        report['serverStarted'] = True
    restore = args.restore_pending or os.environ.get('D2_QA_INPUT','0')!='1'
    if restore and pending.exists():
        states = json.loads(pending.read_text())
        if {(item['card'],item['control']) for item in states}!={(card,control) for card in (0,1) for control in ('Speaker','Headphone')}:
            raise ValueError('Invalid saved mixer switch set')
        for item in states:
            if item['state'] not in ('on','off'):
                raise ValueError('Invalid saved mixer switch state')
            subprocess.run(['amixer','-c',str(item['card']),'sset',item['control'],item['state']],check=True,stdout=subprocess.DEVNULL)
            state = subprocess.check_output(['amixer','-c',str(item['card']),'sget',item['control']],text=True)
            if re.findall(r'Playback \[(on|off)\]',state)[-1]!=item['state']:
                raise RuntimeError('Mixer restoration failed')
        pending.rename(pending.with_name('audio-restored-round2-'+str(time.time_ns())+'.json'))
        report['savedMixerSwitchesRestored'] = True
        sinks = pulse('list','short','sinks').stdout
        headphone = Path('/sys/class/anbernic_misc/spk_state')
        target = 'alsa_output.0.HiFi__Speaker__sink' if headphone.exists() and headphone.read_text().strip()=='1' else 'alsa_output.1.stereo-fallback'
        if target in sinks:
            pulse('set-default-sink',target)
            pulse('set-sink-mute',target,'0')
    report['info'] = pulse('info').stdout
    report['sinks'] = pulse('list','short','sinks').stdout
    if 'auto_null' in report['sinks'] and 'alsa_output' not in report['sinks']:
        raise RuntimeError('Firmware audio exposes only a null sink')
    qa_pending = root/'audio-before-ui-qa.json'
    if args.qa_mute:
        if not qa_pending.exists():
            saved = [{'name':line.split('\t')[1],
                      'muted':pulse('get-sink-mute',line.split('\t')[1]).stdout.strip().endswith('yes')}
                     for line in report['sinks'].splitlines()]
            with qa_pending.open('x') as stream:
                json.dump(saved,stream)
        for line in report['sinks'].splitlines():
            pulse('set-sink-mute',line.split('\t')[1],'1')
        report['qaMuted'] = True
    elif restore and qa_pending.exists():
        for item in json.loads(qa_pending.read_text()):
            pulse('set-sink-mute',item['name'],'1' if item['muted'] else '0')
        qa_pending.rename(qa_pending.with_name('audio-restored-ui-qa-'+str(time.time_ns())+'.json'))
        report['manualAudioRestored'] = True
    print('AUDIO_PREFLIGHT '+json.dumps(report),flush=True)


if __name__=='__main__':
    main()
