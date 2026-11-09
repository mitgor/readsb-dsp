"""Preserve exact failed assertion evidence; never relax any parity gate."""
from pathlib import Path
import sys
D=Path('/dev/shm/adsb-rust-sequence-20261109');source=(D/'code-paired/paired.py').read_text();old="for field,value in [('candidates',candidates),('accepted',accepted),('audit',audit),('decisions',decisions)]:assert ref[field]==value,(mode,case['file'],field)";assert old in source
new="""for field,value in [('candidates',candidates),('accepted',accepted),('audit',audit),('decisions',decisions)]:
   if ref[field]!=value:
    (D/'paired-mismatch.private.json').write_text(json.dumps(dict(mode=mode,file=case['file'],field=field,expected=ref[field],actual=value)))
    raise AssertionError((mode,case['file'],field))"""
source=source.replace(old,new);(D/'code-paired/paired-diagnostic.py').write_text(source)
