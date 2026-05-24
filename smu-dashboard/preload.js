const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('smu', {
  getData: () => ipcRenderer.invoke('get-data'),
  runCommand: (cmd) => ipcRenderer.invoke('run-command', cmd),
  openFolder: (p) => ipcRenderer.invoke('open-folder', p),
})
