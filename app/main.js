'use strict';
const {app,BrowserWindow,ipcMain,dialog,shell,protocol,net}=require('electron');
const fs=require('fs'),fsp=fs.promises,path=require('path'),os=require('os'),crypto=require('crypto');
const {spawn}=require('child_process');const {pathToFileURL}=require('url');
protocol.registerSchemesAsPrivileged([{scheme:'voice',privileges:{standard:true,secure:true,supportFetchAPI:true,stream:true}}]);
app.setName('VoxCPM Desktop');
let win,child=null,busy=false,epoch=0,hardware=null,reference=null,prepared=null;
const media=new Map();const GIB=1024**3;
const root=process.env.VOX_DESKTOP_BUNDLE||path.dirname(app.getAppPath());
const config=JSON.parse(fs.readFileSync(path.join(root,'bundle.json'),'utf8'));
const python=path.join(root,config.python),engine=path.join(root,'engine/job.py'),models=path.join(root,'models');
const data=process.env.VOX_DESKTOP_DATA||app.getPath('userData');fs.mkdirSync(path.join(data,'jobs'),{recursive:true});fs.mkdirSync(path.join(data,'outputs'),{recursive:true});
const settingsFile=path.join(data,'settings.json'),draftFile=path.join(data,'draft.json');
const readJSON=(file,fallback)=>{try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch{return fallback;}};
let settings=readJSON(settingsFile,{configured:false,device:'cpu'});
function save(file,value){const temp=file+'.tmp';fs.writeFileSync(temp,JSON.stringify(value,null,2));fs.renameSync(temp,file);}
function progress(message,extra={}){if(win&&!win.isDestroyed())win.webContents.send('progress',{message,...extra});}
function mediaURL(file){const token=crypto.randomBytes(16).toString('hex');media.set(token,file);return 'voice://local/'+token;}
function kill(p){if(!p||p.exitCode!==null)return;if(process.platform==='win32'){spawn('taskkill',['/pid',String(p.pid),'/T','/F'],{windowsHide:true});}else{try{process.kill(-p.pid,'SIGTERM');}catch{}setTimeout(()=>{if(p.exitCode===null)try{process.kill(-p.pid,'SIGKILL');}catch{}},2000).unref();}}
function job(mode,args={},timeout=180000){return new Promise((resolve,reject)=>{
 if(child)return reject(Error('已有任务在处理，请等待或先停止。'));
 const id=Date.now()+'-'+crypto.randomBytes(4).toString('hex'),file=path.join(data,'jobs',id+'.json');
 const q={...args,mode,data_dir:data,models_dir:models,device:settings.device};save(file,q);
 const log=fs.createWriteStream(path.join(data,'jobs',id+'.log'));
 const p=spawn(python,['-u',engine,file],{cwd:root,env:{...process.env,PYTHONUTF8:'1',PYTHONNOUSERSITE:'1',PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8',HF_HUB_OFFLINE:'1',TRANSFORMERS_OFFLINE:'1',TOKENIZERS_PARALLELISM:'false'},windowsHide:true,detached:process.platform!=='win32'});child=p;
 let buffer='',result=null,error=null;const timer=setTimeout(()=>{error='本次处理超过时限，已停止。请缩短文本或参考音频。';kill(p);},timeout);
 p.stdout.setEncoding('utf8');p.stdout.on('data',b=>{log.write(b);buffer+=b.toString();let index;while((index=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,index);buffer=buffer.slice(index+1);try{const e=JSON.parse(line);if(e.type==='result')result=e.result;else if(e.type==='error')error=e.message;else if(e.type==='progress')progress(e.message);}catch{}}});
 p.stderr.on('data',b=>log.write(b));
 p.on('error',e=>{error=e.message;});
 p.on('close',code=>{clearTimeout(timer);log.end();if(child===p)child=null;if(code===0&&result&&!error)resolve(result);else reject(Error(error||'任务已停止，或运行时未能完成处理。日志已保存在本机。'));});
 });}
async function exclusive(task){if(busy)throw Error('已有任务在处理，请先等待或停止。');busy=true;const token=epoch;try{return await task(()=>{if(token!==epoch)throw Error('已停止。');});}finally{busy=false;progress('就绪',{idle:true});}}
async function scan(installBytes=0,installDir=data){hardware=await job('probe',{install_bytes:installBytes,install_dir:installDir},90000);return hardware;}
function ensureReady(){if(!hardware?.supported)throw Error('请先在“安装与设备”完成配置检测。');if(!settings.configured)throw Error('请先确认设备配置。');}
function refArgs(v){return {reference:reference.path,start:Number(v.start)||0,clip_seconds:Number(v.clipSeconds)||30,language:v.language||null};}
function sameRef(v){return prepared&&reference&&prepared.selection===reference.id&&prepared.start===Number(v.start||0)&&prepared.clipSeconds===Number(v.clipSeconds||30)&&prepared.language===(v.language||'');}
async function recognize(v,check){ensureReady();if(!reference)throw Error('请先选择参考音频。');const chosen=reference.id;const args=refArgs(v);progress('正在转换参考音频、识别台词…');const r=await job('recognize',args,180000);check();if(reference.id!==chosen)throw Error('参考音频已更换，请重新识别。');prepared={...r,selection:chosen,start:Number(v.start)||0,clipSeconds:Number(v.clipSeconds)||30,language:v.language||''};return {...r,preview:mediaURL(r.reference.file)};}
ipcMain.handle('bootstrap',()=>({version:'1.0.0',platform:process.platform,dataDir:data,settings,draft:readJSON(draftFile,{}),models:['VoxCPM2','Qwen3-ASR-1.7B'],installed:app.getPath('exe').startsWith(installTarget())}));
ipcMain.handle('scan',()=>exclusive(()=>scan()));
ipcMain.handle('configure',async(_,device)=>{if(busy)throw Error('请等待当前任务完成。');if(!hardware?.supported)throw Error('配置检测未通过。');const valid=['cpu'];if(hardware.mps_available)valid.push('mps');if(hardware.cuda_available&&hardware.vram_bytes>=8*GIB)valid.push('cuda');if(!valid.includes(device))throw Error('当前设备不可用。');settings={configured:true,device};save(settingsFile,settings);return settings;});
ipcMain.handle('chooseReference',async()=>{if(busy)throw Error('请等待或停止当前任务。');const r=await dialog.showOpenDialog(win,{title:'选择想要模仿的参考声音',properties:['openFile'],filters:[{name:'音频和带音轨的视频',extensions:['wav','mp3','m4a','aac','flac','ogg','opus','aiff','aif','wma','mp4','webm']}]});if(r.canceled)return null;const p=r.filePaths[0];if(fs.statSync(p).size>500*1024**2)throw Error('请选择小于 500 MB 的文件。');reference={id:crypto.randomBytes(8).toString('hex'),path:p,name:path.basename(p)};prepared=null;return {name:reference.name};});
ipcMain.handle('removeReference',()=>{if(busy)throw Error('请先停止当前处理。');reference=null;prepared=null;return true;});
ipcMain.handle('recognize',(_,v)=>exclusive(check=>recognize(v,check)));
ipcMain.handle('generate',(_,v)=>exclusive(async check=>{ensureReady();let r=null;if(reference){if(!sameRef(v)){if(String(v.transcript||'').trim()){const args=refArgs(v);const converted=await job('prepare',args,100000);check();prepared={...converted,selection:reference.id,start:Number(v.start)||0,clipSeconds:Number(v.clipSeconds)||30,language:v.language||'',transcript:v.transcript};}else{r=await recognize(v,check);v.transcript=r.transcript;}}check();}const q={text:String(v.text||''),style:String(v.style||''),steps:Number(v.steps)||10,seed:Number.isFinite(Number(v.seed))?Number(v.seed):42,transcript:reference?String(v.transcript||''):'',reference_info:reference?prepared.reference:null};const result=await job('generate',q,settings.device==='cpu'?1200000:600000);check();return {...result,url:mediaURL(result.file),recognized:r};}));
ipcMain.handle('stop',()=>{epoch++;if(child)kill(child);progress('正在停止并释放模型…');return true;});
ipcMain.handle('saveDraft',(_,draft)=>{const allowed=['text','style','steps','seed','start','clipSeconds','language','auto'];save(draftFile,Object.fromEntries(allowed.map(k=>[k,draft[k]])));return true;});
ipcMain.handle('openOutputs',()=>shell.openPath(path.join(data,'outputs')));
function bundleSource(){return process.platform==='darwin'?path.resolve(process.execPath,'../../..'):path.dirname(process.execPath);}
function installTarget(){return process.platform==='darwin'?path.join(os.homedir(),'Applications','VoxCPM Desktop.app'):path.join(process.env.LOCALAPPDATA||os.homedir(),'Programs','VoxCPM Desktop');}
async function bytes(dir){let n=0;for(const e of await fsp.readdir(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())n+=await bytes(p);else if(e.isFile())n+=(await fsp.stat(p)).size;}return n;}
ipcMain.handle('install',()=>exclusive(async check=>{
 const source=bundleSource(),target=installTarget();if(path.resolve(source)===path.resolve(target))return {installed:true,path:target,message:'已经安装在目标位置。'};
 if(fs.existsSync(target))throw Error('目标位置已有同名 App，为避免覆盖，请先使用已有版本或将其移走。');
 progress('正在检查安装空间…');const total=await bytes(source);await fsp.mkdir(path.dirname(target),{recursive:true});const report=await scan(total,target);if(!report.supported)throw Error(report.reasons.join('\n'));check();
 const staging=target+'.installing-'+Date.now();progress('正在复制 App、两个模型和运行环境…');
 try{await fsp.cp(source,staging,{recursive:true,dereference:false,verbatimSymlinks:true,errorOnExist:true,force:false,mode:fs.constants.COPYFILE_FICLONE});check();await fsp.rename(staging,target);}catch(e){await fsp.rm(staging,{recursive:true,force:true});throw e;}
 settings={configured:true,device:report.device};save(settingsFile,settings);
 if(process.platform==='win32'){
  const executable=path.join(target,'VoxCPM Desktop.exe'),desktop=path.join(app.getPath('desktop'),'VoxCPM Desktop.lnk');
  shell.writeShortcutLink(desktop,'create',{target:executable,cwd:target,description:'本地语音生成与声音克隆'});
 }
 return {installed:true,path:target,message:process.platform==='darwin'?'已安装到个人“应用程序”文件夹。':'已安装，并添加桌面快捷方式。',device:report.device};
}));
if(!app.requestSingleInstanceLock())app.quit();else{
 app.on('second-instance',()=>{if(win){if(win.isMinimized())win.restore();win.focus();}});
 app.whenReady().then(()=>{
 protocol.handle('voice',request=>{const token=new URL(request.url).pathname.slice(1),file=media.get(token);if(!file)return new Response('Not found',{status:404});return net.fetch(pathToFileURL(file).toString());});
 win=new BrowserWindow({width:1120,height:900,minWidth:840,minHeight:680,title:'VoxCPM Desktop',icon:path.join(__dirname,'assets/icon.png'),backgroundColor:'#10131c',webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));win.webContents.on('will-navigate',(e,url)=>{if(!url.startsWith(pathToFileURL(__dirname).toString()))e.preventDefault();});
 win.loadFile(path.join(__dirname,'index.html'));win.on('closed',()=>{win=null;});
 });
 app.on('before-quit',()=>{epoch++;if(child)kill(child);});app.on('window-all-closed',()=>app.quit());
}
