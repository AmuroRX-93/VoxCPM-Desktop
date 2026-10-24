"""Desktop engine: one subprocess per bounded operation; models never overlap."""
from pathlib import Path
import os,sys,json,time,hashlib,subprocess,wave,traceback,math,re
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'vendor'))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false',PYTORCH_ENABLE_MPS_FALLBACK='1')
def event(kind,**args):print(json.dumps(dict(type=kind,**args),ensure_ascii=False),flush=True)
def atomic(path,data):
 p=Path(path);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8");tmp.replace(p)
def convert(q):
 import imageio_ffmpeg
 p=Path(q['reference']);start=float(q.get('start',0));duration=float(q.get('clip_seconds',30))
 if not p.is_file()or p.stat().st_size>500*1024**2:raise ValueError('文件不存在或超过 500 MB。')
 if not math.isfinite(start)or start<0:raise ValueError('起点不能小于 0。')
 if not math.isfinite(duration)or not 1<=duration<=30:raise ValueError('参考长度须在 1～30 秒之间。')
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 source_sha=h.hexdigest();key=hashlib.sha256(f'{source_sha}:{start:.4f}:{duration:.4f}:pcm16-v1'.encode()).hexdigest()
 out=Path(q['data_dir'])/'reference-cache';out.mkdir(parents=True,exist_ok=True);wav=out/(key+'.wav')
 if not wav.exists():
  temp=out/(key+'.partial.wav')
  try:
   r=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-nostdin','-y','-ss',str(start),'-i',str(p),'-map','0:a:0','-t',str(duration),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(temp)],capture_output=True,text=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32'else 0)
   if r.returncode:raise ValueError('无法解码音频，请检查文件是否损坏或没有音轨。'+r.stderr[-300:])
   with wave.open(str(temp))as f:
    seconds=f.getnframes()/f.getframerate()
    if seconds<1:raise ValueError('所选起点之后不足 1 秒，请调整截取起点。')
   temp.replace(wav)
  finally:
   if temp.exists():temp.unlink()
 with wave.open(str(wav))as f:seconds=f.getnframes()/f.getframerate()
 return dict(key=key,file=str(wav),source_name=p.name,source_sha256=source_sha,start=start,seconds=seconds)
def recognize(q):
 info=convert(q);event('progress',message='参考片段已准备，正在识别原台词…',reference=info)
 lang=q.get('language')or None;cache=Path(info['file']).with_suffix('.'+hashlib.sha256(str(lang).encode()).hexdigest()[:8]+'.json')
 if cache.exists():return dict(reference=info,**json.loads(cache.read_text(encoding="utf-8")),cached=True)
 import torch,numpy as np,soundfile as sf
 from transformers import AutoProcessor,AutoModelForMultimodalLM
 device=q.get('device','cpu');dtype=torch.float32 if device in ['cpu','mps']else torch.float16
 model_path=Path(q['models_dir'])/'Qwen3-ASR-1.7B'
 model=AutoModelForMultimodalLM.from_pretrained(model_path,local_files_only=True,dtype=dtype,attn_implementation='eager').to(device)
 processor=AutoProcessor.from_pretrained(model_path,local_files_only=True)
 audio,sr=sf.read(info['file'],dtype='float32');assert sr==16000
 inputs=processor.apply_transcription_request(audio=audio,language=lang).to(device,dtype)
 with torch.inference_mode():
  ids=model.generate(**inputs,max_new_tokens=512,do_sample=False)
 generated=ids[:,inputs['input_ids'].shape[1]:]
 text=processor.decode(generated,return_format='transcription_only')[0].strip()
 if not text:raise ValueError('没有识别出台词。请换一段清晰的人声，或手动填写参考原话。')
 result=dict(transcript=text,language=lang,model='Qwen3-ASR-1.7B-hf');atomic(cache,result)
 return dict(reference=info,**result,cached=False)
def synthesize(q):
 import torch,numpy as np,soundfile as sf
 from voxcpm import VoxCPM
 text=q.get('text','').strip()
 if not text or len(text)>500:raise ValueError('请输入 1～500 字的目标台词，长内容建议按段生成。')
 dev=q.get('device','cpu');steps=int(q.get('steps',10));seed=int(q.get('seed',42))
 if dev not in ['cpu','mps','cuda']or not 4<=steps<=20:raise ValueError('生成参数不合法。')
 kwargs={};ref=q.get('reference_info');transcript=q.get('transcript','').strip()
 if ref:
  if not Path(ref['file']).is_file():raise ValueError('参考音频失效，请重新上传。')
  kwargs['reference_wav_path']=ref['file']
  if transcript:kwargs.update(prompt_wav_path=ref['file'],prompt_text=transcript)
 event('progress',message='正在加载语音模型…')
 model=VoxCPM.from_pretrained(str(Path(q['models_dir'])/'VoxCPM2'),device=dev,optimize=False,load_denoiser=False,local_files_only=True)
 style=re.sub(r'[()（）]','',q.get('style','')).strip();source=('('+style+')'if style else '')+text
 event('progress',message='正在生成语音…')
 start=time.monotonic()
 wav=model.generate(text=source,seed=seed,normalize=False,denoise=False,retry_badcase=False,inference_timesteps=steps,max_len=2048,**kwargs)
 if len(wav)==0 or not np.isfinite(wav).all()or np.max(np.abs(wav))<.0001:raise ValueError('模型返回了无效音频，请修改文字或随机种子重试。')
 out=Path(q['data_dir'])/'outputs';out.mkdir(parents=True,exist_ok=True)
 path=out/(time.strftime('%Y%m%d_%H%M%S')+'_'+os.urandom(3).hex()+'.wav');sf.write(path,wav,model.tts_model.sample_rate)
 result=dict(file=str(path),seconds=len(wav)/model.tts_model.sample_rate,sample_rate=model.tts_model.sample_rate,generation_seconds=time.monotonic()-start,device=dev)
 atomic(path.with_suffix('.json'),dict(request=q,result=result));return result
def main():
 q=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"));mode=q['mode']
 os.environ['HF_HOME']=str(Path(q['data_dir'])/'hf-cache')
 if mode=='probe':
  from hardware import probe
  result=probe(q.get('install_dir',q['data_dir']),q.get('install_bytes',0))
 elif mode=='prepare':result=dict(reference=convert(q))
 elif mode=='recognize':result=recognize(q)
 elif mode=='generate':result=synthesize(q)
 else:raise ValueError('未知操作')
 event('result',result=result)
if __name__=='__main__':
 try:main()
 except Exception as e:
  traceback.print_exc(file=sys.stderr);event('error',message=str(e));sys.exit(1)
