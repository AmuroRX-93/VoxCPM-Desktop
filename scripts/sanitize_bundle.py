"""Remove host-specific generated caches and unused cross-built console scripts."""
from pathlib import Path
import argparse, shutil, json, subprocess
p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);a=p.parse_args()
r=a.bundle
assert (r/'Contents/Resources/bundle.json').is_file() or (r/'resources/bundle.json').is_file()
removed=[]
lib=r/'Contents/Resources/python/lib/libpython3.12.dylib'
if lib.is_file():
 ident=subprocess.check_output(['otool','-D',str(lib)],text=True).splitlines()[-1].strip()
 if ident.startswith('/Users/'):
  subprocess.run(['install_name_tool','-id','@rpath/libpython3.12.dylib',str(lib)],check=True)
  print('Relocated libpython identity; re-sign the bundle before distribution')
for d in sorted(r.rglob('__pycache__'),key=lambda p:len(p.parts),reverse=True):
 if d.is_dir():
  removed.append(d.relative_to(r).as_posix());shutil.rmtree(d)
for f in r.rglob('*'):
 if f.is_file() and f.suffix in ['.pyc','.pyo','.nbc','.nbi']:
  removed.append(f.relative_to(r).as_posix());f.unlink()
b=r/'resources/python/Lib/site-packages/bin'
if b.is_dir():
 removed.append(b.relative_to(r).as_posix());shutil.rmtree(b)
print(json.dumps({'removed_generated_items':len(removed),'items':removed},ensure_ascii=False))
