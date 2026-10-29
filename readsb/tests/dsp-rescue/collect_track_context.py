#!/usr/bin/env python3
"""Bounded independent network track context for live phase shadow.

adsb.fi supplies aircraft-level reference only. This does not prove any
particular corrected ADS-B payload or imply a packet was decoded independently.
Personal, non-commercial research use; source attribution is preserved.
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

SOURCE = 'https://opendata.adsb.fi'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=int, default=1200)
    parser.add_argument('--period', type=int, default=30)
    parser.add_argument('--lat', type=float, default=52.4256)
    parser.add_argument('--lon', type=float, default=13.1556)
    args = parser.parse_args()
    if not 60 <= args.duration <= 3600 or not 20 <= args.period <= 120:
        parser.error('invalid duration or period')
    url = f'{SOURCE}/api/v3/lat/{args.lat}/lon/{args.lon}/dist/250'
    deadline = time.monotonic()+args.duration
    with args.output.open('a') as output:
        while time.monotonic() < deadline:
            started = time.monotonic()
            row = {'queried_unix': time.time(), 'source': SOURCE,
                   'attribution': 'Aircraft context: adsb.fi — https://adsb.fi',
                   'packet_truth': False}
            try:
                request = urllib.request.Request(
                    url, headers={'User-Agent':'readsb-dsp-personal-research/1.0',
                                  'Accept':'application/json'})
                with urllib.request.urlopen(request, timeout=8) as response:
                    blob = response.read(2*1024*1024+1)
                if len(blob) > 2*1024*1024:
                    raise ValueError('oversize response')
                data = json.loads(blob)
                stamp = data['now']/1000 if data['now'] > 1e11 else data['now']
                if not -5 <= row['queried_unix']-stamp <= 30:
                    raise ValueError('stale external response')
                rows = data.get('ac', data.get('aircraft', []))
                if not isinstance(rows, list) or len(rows) > 10000:
                    raise ValueError('invalid aircraft list')
                row['source_unix'] = stamp
                row['aircraft'] = []
                for a in rows:
                    if not isinstance(a, dict) or not all(k in a for k in ('hex','lat','lon','seen_pos')):
                        continue
                    if a.get('type') != 'adsb_icao' or a.get('mlat') or a.get('tisb'):
                        continue
                    if not isinstance(a['seen_pos'], (int,float)) or not 0 <= a['seen_pos'] <= 30:
                        continue
                    if not isinstance(a['hex'], str) or len(a['hex']) != 6:
                        continue
                    row['aircraft'].append({
                        'hex': a['hex'], 'lat': a['lat'], 'lon': a['lon'],
                        'seen_pos': a['seen_pos']})
            except Exception as error:
                row['error'] = repr(error)
            output.write(json.dumps(row, separators=(',', ':'))+'\n')
            output.flush()
            time.sleep(min(max(0, args.period-(time.monotonic()-started)),
                           max(0, deadline-time.monotonic())))


if __name__ == '__main__':
    main()
