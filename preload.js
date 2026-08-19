const { ipcRenderer, desktopCapturer } = require('electron');

window.ipcRenderer = ipcRenderer;
window.desktopCapturer = desktopCapturer;
