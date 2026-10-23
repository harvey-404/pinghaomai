"""Verify the published baseline against immutable Git object contents, without credentials."""
from pathlib import Path
import hashlib, json, subprocess, sys

root=Path(__file__).resolve().parents[1]
doc=json.loads((root/'docs/evidence/baseline-manifest.json').read_text(encoding='utf-8'))
errors=[]
for item in doc['files']:
    r=subprocess.run(['git','show',doc['baseline_commit']+':'+item['path']],cwd=root,capture_output=True)
    if r.returncode or hashlib.sha256(r.stdout).hexdigest()!=item['sha256']:
        errors.append(item['path'])
if errors:
    for path in errors:print('FAIL baseline:',path)
    sys.exit(1)
print('PASS:',len(doc['files']),'baseline Git blobs match SHA-256 manifest')
print('This verifies content only; it is not proof of authorship or a trusted historical timestamp.')
