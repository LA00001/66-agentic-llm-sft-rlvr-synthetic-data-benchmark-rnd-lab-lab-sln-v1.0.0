from __future__ import annotations
from pathlib import Path
import hashlib, json

def _sha256(path: Path) -> str:
    h=hashlib.sha256();
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(65536),b''): h.update(chunk)
    return h.hexdigest()

def load_evidence(root: str|Path) -> dict:
    root=Path(root); manifest=root/'evidence'/'manifest.json'
    if not manifest.exists(): return {"available":False,"status":"NO_EVIDENCE","proofs":[]}
    data=json.loads(manifest.read_text(encoding='utf-8')); proofs=[]; ok=True
    for p in data.get('proofs',[]):
        fp=root/'evidence'/p['file']; exists=fp.exists(); checksum=_sha256(fp) if exists else None; valid=exists and checksum==p.get('sha256')
        ok &= valid
        proofs.append({**p,"exists":exists,"checksum_valid":valid})
    return {"available":True,"status":"VALIDATED" if ok else "STALE","project_version":data.get('project_version'),"proofs":proofs,"levels":data.get('levels',[])}
