from pathlib import Path
import platform,os,sys,json,shutil,subprocess,ctypes
GIB=1024**3
def physical_ram():
 if sys.platform=='win32':
  class Memory(ctypes.Structure):_fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong)for n in ['totalPhys','availPhys','totalPage','availPage','totalVirtual','availVirtual','availExtended']]
  m=Memory();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.totalPhys
 if sys.platform=='darwin':return int(subprocess.check_output(['sysctl','-n','hw.memsize'],text=True,timeout=5))
 return os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
def assess(info,install_bytes=0):
 reasons=[];warnings=[];ram=info['ram_bytes'];free=info['free_bytes'];arch=info['arch'].lower();osname=info['platform']
 if not((osname=='darwin'and arch in ['arm64','aarch64'])or(osname=='win32'and arch in ['amd64','x86_64'])):reasons.append('本安装包支持 Apple 芯片 Mac 和 Windows x64；当前系统架构不匹配。')
 if osname=='darwin'and tuple(int(x)for x in info.get('os_version','0').split('.')[:2])<(13,0):reasons.append('此版本需要 macOS 13 或更新版本。')
 if osname=='win32'and int(info.get('os_build',0))<17763:reasons.append('此版本需要 Windows 10 1809 或更新版本。')
 if ram<15*GIB:reasons.append('内存不足：本包按至少 16 GB 物理内存设计。')
 elif ram<31*GIB:warnings.append('内存接近最低配置，建议关闭其他大型程序；32 GB 及以上更稳妥。')
 required=max(8*GIB,install_bytes+8*GIB)
 if free<required:reasons.append(f'剩余空间不足：目标磁盘至少还需要 {required/GIB:.1f} GB 空间（含安装及工作空间）。')
 if info.get('cuda_available')and info.get('vram_bytes',0)>=8*GIB:device='cuda'
 elif info.get('mps_available'):device='mps'
 else:
  device='cpu';warnings.append('将使用 CPU，语音生成可能明显较慢。')
  if info.get('cuda_available'):warnings.append('显存低于 8 GB，默认不用该显卡加载完整语音模型。')
 if not info.get('torch_ok'):reasons.append('推理运行时未通过实际张量运算检查。')
 return dict(supported=not reasons,device=device,reasons=reasons,warnings=warnings,required_free_bytes=required,status='不适合安装'if reasons else('可用，但有性能提示'if warnings else'配置适合'))
def probe(data_dir,install_bytes=0):
 p=Path(data_dir)
 while not p.exists():p=p.parent
 info=dict(platform=sys.platform,arch=platform.machine(),os_version=platform.mac_ver()[0]if sys.platform=='darwin'else platform.version(),os_build=sys.getwindowsversion().build if sys.platform=='win32'else 0,ram_bytes=physical_ram(),free_bytes=shutil.disk_usage(p).free,cpu=platform.processor()or platform.machine(),cpu_cores=os.cpu_count(),torch_ok=False,cuda_available=False,mps_available=False,gpu='CPU')
 try:
  import torch
  info['torch_version']=torch.__version__;info['cuda_available']=torch.cuda.is_available();info['mps_available']=torch.backends.mps.is_available()
  if info['cuda_available']:
   info['vram_bytes']=torch.cuda.get_device_properties(0).total_memory;info['gpu']=torch.cuda.get_device_name(0)
  elif info['mps_available']:info['gpu']='Apple Silicon / Metal（共享内存）'
  dev='cuda'if info['cuda_available']else('mps'if info['mps_available']else'cpu')
  x=torch.ones((256,256),device=dev);assert abs((x@x)[0,0].item()-256)<.01
  info['torch_ok']=True
 except Exception as e:info['runtime_error']=str(e)
 info.update(assess(info,install_bytes));return info
