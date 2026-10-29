"""Verify saved release candidates against the receiver validation manifest."""
import hashlib,json,sys
from pathlib import Path
manifest=json.loads(Path(sys.argv[1]).read_text());root=Path(sys.argv[2])
for name,expected in manifest['candidate_sha256'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
print('Release candidate SHA-256 verified')
