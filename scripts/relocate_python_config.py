"""Remove build-machine paths from a standalone macOS Python sysconfig file."""
import argparse, ast, pprint
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('python_root',type=Path);a=p.parse_args()
for f in a.python_root.glob('lib/python*/_sysconfigdata__darwin_darwin.py'):
 tree=ast.parse(f.read_text())
 node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='build_time_vars' for t in n.targets))
 data=ast.literal_eval(node.value);prefix=data.get('prefix','')
 if not prefix or not prefix.startswith('/Users/'):raise RuntimeError('Expected build-machine prefix absent; inspect before rewriting')
 data={k:(v.replace(prefix,'__VOXCPM_PYTHON_ROOT__') if isinstance(v,str) else v) for k,v in data.items()}
 s='# Runtime-relative build paths for the redistributed standalone Python.\nimport sys as _sys\nbuild_time_vars = '+pprint.pformat(data,sort_dicts=True)+'\n'
 s+="build_time_vars = {k: (v.replace('__VOXCPM_PYTHON_ROOT__', _sys.prefix) if isinstance(v, str) else v) for k, v in build_time_vars.items()}\n"
 compile(s,str(f),'exec');f.write_text(s)
 print('Relocated',f.name)
