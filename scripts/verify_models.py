from pathlib import Path
import hashlib,json,sys
root=Path(sys.argv[1]);manifest=json.loads((Path(__file__).resolve().parents[1]/"models-manifest.json").read_text())
for name,m in manifest.items():
 for rel,expected in m["files"].items():
  file=root/name/rel
  assert file.is_file() and file.stat().st_size==expected["bytes"],str(file)
  h=hashlib.sha256()
  with file.open("rb") as f:
   for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
  assert h.hexdigest()==expected["sha256"],str(file)
 print(name,"verified")
