"""Assemble preverified offline inputs; run on macOS for a Mac bundle."""
from pathlib import Path
import argparse,shutil,zipfile,json,subprocess,plistlib,os
p=argparse.ArgumentParser();p.add_argument('--platform',choices=['darwin-arm64','win32-x64'],required=True)
for arg in ['runtime','models','electron-zip','output']:p.add_argument('--'+arg,type=Path,required=True)
a=p.parse_args();source=Path(__file__).resolve().parents[1]
if a.output.exists():p.error('Output must be a new directory')
for f in [a.runtime,a.models,a.electron_zip]:
 if not f.exists():p.error(f'Missing input: {f}')
subprocess.run([os.sys.executable,str(source/'scripts/verify_models.py'),str(a.models)],check=True)
a.output.mkdir(parents=True)
if a.platform=='darwin-arm64':
 subprocess.run(['ditto','-x','-k',str(a.electron_zip),str(a.output)],check=True)
 app=a.output/'VoxCPM Desktop.app';(a.output/'Electron.app').rename(app);root=app/'Contents/Resources';pyrel='python/bin/python3.12'
 info=app/'Contents/Info.plist';v=plistlib.loads(info.read_bytes());v.update(CFBundleDisplayName='VoxCPM Desktop',CFBundleName='VoxCPM Desktop',CFBundleIdentifier='local.voxcpm.desktop',CFBundleShortVersionString='1.0.0',CFBundleVersion='1.0.0',LSMinimumSystemVersion='13.0');info.write_bytes(plistlib.dumps(v))
else:
 with zipfile.ZipFile(a.electron_zip)as z:z.extractall(a.output)
 (a.output/'electron.exe').rename(a.output/'VoxCPM Desktop.exe');root=a.output/'resources';pyrel='python/python.exe'
root.mkdir(exist_ok=True)
for src,dst in [(source/'app',root/'app'),(source/'engine',root/'engine'),(a.runtime,root/'python'),(a.models,root/'models')]:
 shutil.copytree(src,dst,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.cache'))
# Models must be physical files in the output, not external working-tree symlinks.
for name in ['VoxCPM2','Qwen3-ASR-1.7B']:
 dest=root/'models'/name
 if dest.is_symlink():dest.unlink();shutil.copytree((a.models/name).resolve(),dest,ignore=shutil.ignore_patterns('.cache'))
if a.platform=='win32-x64' and (root/'python/python').is_symlink():
 (root/'python/python').unlink()
if a.platform=='darwin-arm64':shutil.copy2(source/'app/assets/app.icns',root/'electron.icns')
(root/'bundle.json').write_text(json.dumps(dict(version='1.0.0',python=pyrel,platform=a.platform),indent=2),encoding='utf-8')
licenses=root/'licenses';licenses.mkdir(exist_ok=True)
for f in a.output.glob('LICENSE*'):shutil.copy2(f,licenses/f.name)
shutil.copy2(source/'LICENSE',licenses/'Desktop-MIT.txt');shutil.copy2(source/'engine/vendor/LICENSE-VoxCPM',licenses/'VoxCPM-Apache-2.0.txt')
for f in (source/'docs').glob('*LICENSE*'):shutil.copy2(f,licenses/f.name)
shutil.copy2(source/'docs/THIRD_PARTY.md',licenses/'THIRD_PARTY.md');shutil.copy2(source/'README.md',a.output/'README.md')
for f in root.rglob('*.pth'):
 text=f.read_text(errors='replace')
 if '/Users/'in text or '\\Users\\'in text:raise RuntimeError(f'Nonportable path in {f}')
print(a.output)
