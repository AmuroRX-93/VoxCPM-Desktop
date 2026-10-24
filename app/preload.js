const {contextBridge,ipcRenderer}=require('electron');
const methods=['bootstrap','scan','chooseReference','recognize','generate','stop','saveDraft','configure','install','openOutputs','removeReference'];
contextBridge.exposeInMainWorld('voice',Object.fromEntries(methods.map(name=>[name,(...args)=>ipcRenderer.invoke(name,...args)]).concat([['onProgress',cb=>{ipcRenderer.on('progress',(_,data)=>cb(data));}]])));
