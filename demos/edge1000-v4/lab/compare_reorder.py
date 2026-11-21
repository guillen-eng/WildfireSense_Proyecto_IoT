"""Repeatable OFFLINE comparison of bounded event-time buffering on one scenario.

Zero=existing Edge behavior. Nonzero=experimental evaluation helper only.
SOS is always consumed immediately if a frame is delivered; real MQTT and
physical radio timing are not simulated.
"""

import argparse
import json
from pathlib import Path
from lab.robustness import evaluate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--file',type=Path,default=Path('data/scenarios/fuego_rapido.jsonl'))
    p.add_argument('--loss',type=float,default=.05)
    p.add_argument('--duplicates',type=float,default=.02)
    p.add_argument('--jitter-s',type=float,default=10)
    p.add_argument('--window-s',type=float,default=12)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--out',type=Path,default=Path('resultados/reordenacion_comparada.json'))
    a=p.parse_args()
    originals=[json.loads(line) for line in a.file.open(encoding='utf-8')]
    truth=a.file.with_name(a.file.stem+'_verdad.json')
    truth_onset=None
    if truth.is_file():
        val=json.loads(truth.read_text(encoding='utf-8'))
        truth_onset=1784073600+val['t0_s']
    old=evaluate(originals,loss=a.loss,duplicates=a.duplicates,
                 jitter_s=a.jitter_s,seed=a.seed,truth_onset=truth_onset,
                 reorder_window_s=0)
    experimental=evaluate(originals,loss=a.loss,duplicates=a.duplicates,
                          jitter_s=a.jitter_s,seed=a.seed,truth_onset=truth_onset,
                          reorder_window_s=a.window_s)
    fields=['delivered_messages','accepted_readings','rejected_order_or_duplicate',
            'first_suspected_fire_timestamp','first_suspected_fire_available_timestamp',
            'suspected_fire_delay_s','first_alarm_available_delay_s','decisions']
    result=dict(
        scope='Offline application-layer scheduling; NOT live Edge, MQTT QoS or RF',
        source=str(a.file),seed=a.seed,settings=dict(loss=a.loss,duplicates=a.duplicates,
            jitter_s=a.jitter_s,reorder_window_s=a.window_s),
        old={k:old.get(k) for k in fields},
        buffered={**{k:experimental.get(k) for k in fields},**experimental['reorder']},
        recovered_readings=experimental['accepted_readings']-old['accepted_readings'],
        caution='Buffering may delay time-critical alerts. Never buffer SOS.',
    )
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
