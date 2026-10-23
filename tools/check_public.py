"""Check the publishable tree without ever printing matched secret content."""
from pathlib import Path
import re, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
try:
    result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True)
    files=[ROOT/p for p in result.stdout.decode().split('\0') if p]
except (OSError,subprocess.CalledProcessError):
    files=[p for p in ROOT.rglob('*') if p.is_file() and not any(x in p.parts for x in ('.git','__pycache__'))]
if not files:files=[p for p in ROOT.rglob('*') if p.is_file() and not any(x in p.parts for x in ('.git','__pycache__'))]
patterns=[re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),re.compile(rb'github_pat_[A-Za-z0-9_]{20,}'),
          re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
          re.compile(rb'Bearer\s+[A-Za-z0-9_-]{24,}'),
          re.compile(rb'(?i)(?:MCD_TOKEN|Authorization)\s*[=:]\s*[\x22\x27][A-Za-z0-9_-]{24,}[\x22\x27]')]
problems=[]
for p in files:
    relative=p.relative_to(ROOT).as_posix()
    if p.suffix in ('.sqlite3','.sqlite','.db','.log','.jsonl','.pem','.key','.pfx') or p.name=='.env' or '.env.' in p.name:
        problems.append((relative,'runtime/private file'))
    raw=p.read_bytes()
    if any(pattern.search(raw) for pattern in patterns):problems.append((relative,'credential pattern'))
if problems:
    for path,kind in problems:print(f'FAIL {path}: {kind}')
    sys.exit(1)
print(f'PASS: {len(files)} public files; no forbidden runtime files or known credential patterns')
