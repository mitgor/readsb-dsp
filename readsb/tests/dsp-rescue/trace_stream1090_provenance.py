#!/usr/bin/env python3
"""Instrument pinned Stream1090 for per-packet repair provenance on stderr.

Only for offline validation; it does not alter normal stdout packets. Run
against a clean checkout of commit 2189bdaca1d62d5e88600b21a281ccc5c18012f2,
then rebuild stream1090. Markers: C clean, T fixed table, E erasure, D DF19.
"""
import argparse
from pathlib import Path
import subprocess

PIN = '2189bdaca1d62d5e88600b21a281ccc5c18012f2'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('repo', type=Path)
    args = p.parse_args()
    rev = subprocess.check_output(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'], text=True).strip()
    if rev != PIN:
        raise SystemExit(f'expected {PIN}, got {rev}')
    path = args.repo/'include/DemodCore.hpp'
    if subprocess.check_output(['git', '-C', str(args.repo), 'status', '--porcelain',
                                '--', 'include/DemodCore.hpp']).strip():
        raise SystemExit('DemodCore.hpp must be clean before instrumentation')
    original = path.read_bytes()
    crlf = b'\r\n' in original
    source = original.decode().replace('\r\n', '\n')
    changes = [
        ("const ICAOTable::Iterator& it) {\n\t\tauto& e = m_cache.getMsgStatEntry(it);",
         "const ICAOTable::Iterator& it, char provenance = 'C') {\n\t\tauto& e = m_cache.getMsgStatEntry(it);"),
        ('\t\tm_messageHandler.handleLong(m_currTime, frame);',
         "\t\tif (downlinkFormat == 17) {\n"
         "\t\t\tstd::cerr << provenance;\n"
         "\t\t\tAVRWriter trace(std::cerr);\n"
         "\t\t\ttrace.write_long_MLAT(MLAT::sampleIndexToMlatTime<NumStreams>(m_currTime), frame);\n"
         "\t\t}\n"
         "\t\tm_messageHandler.handleLong(m_currTime, frame);"),
        ('return sendFrameLongAligned(streamIndex, downlinkFormat, crc, frame, e);',
         "return sendFrameLongAligned(streamIndex, downlinkFormat, crc, frame, e, wasDf19 ? 'D' : 'C');"),
        ('return sendFrameLongAligned(streamIndex, downlinkFormat, crc, toRepair, e);',
         "return sendFrameLongAligned(streamIndex, downlinkFormat, crc, toRepair, e, 'T');"),
        ('return sendFrameLongAligned(streamIndex, downlinkFormat, crc, repaired, e);',
         "return sendFrameLongAligned(streamIndex, downlinkFormat, crc, repaired, e, 'E');"),
    ]
    for old, new in changes:
        if old not in source:
            raise SystemExit(f'expected source marker missing: {old[:60]}')
        source = source.replace(old, new, 1)
    path.write_bytes((source.replace('\n', '\r\n') if crlf else source).encode())
    print(path)


if __name__ == '__main__':
    main()
