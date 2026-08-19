const { app, BrowserWindow, session, desktopCapturer, screen, ipcMain } = require('electron');
const path = require('path');

// 1. Disable D3D11 shared surface capture which causes black frames on Windows DWM
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion,UseChromeOSDirectVideoDecoder');
app.commandLine.appendSwitch('force-wave-audio');
app.commandLine.appendSwitch('enable-usermedia-screen-capturing');
app.commandLine.appendSwitch('allow-http-screen-capture');

// 2. Hardware acceleration and zero-copy performance flags
app.commandLine.appendSwitch('enable-gpu-rasterization');
app.commandLine.appendSwitch('enable-zero-copy');
app.commandLine.appendSwitch('ignore-gpu-blocklist');

// 3. Force DXGI video duplication and lock frame rate rendering
if (process.platform === 'win32') {
  app.commandLine.appendSwitch('enable-features', 'DxgiVideoDecoder,MediaFoundationVideoCapture');
  // Prevents Chromium from throttling offscreen/background paint buffers
  app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
}

function setupMediaPermissions() {
  if (!session.defaultSession) return;

  ipcMain.handle('get-desktop-sources', async () => {
    try {
      const sources = await desktopCapturer.getSources({ types: ['screen'] });
      let targetSource = sources[0];
      const activeWin = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
      if (activeWin && screen) {
        const currentDisplay = screen.getDisplayMatching(activeWin.getBounds());
        const currentDisplayId = currentDisplay.id.toString();
        const matchingDisplay = sources.find(
          (s) => s.display_id === currentDisplayId || s.id.endsWith(`:${currentDisplayId}`)
        );
        if (matchingDisplay) {
          targetSource = matchingDisplay;
        }
      }
      return targetSource ? targetSource.id : (sources[0] ? sources[0].id : null);
    } catch (e) {
      console.error('get-desktop-sources IPC error:', e);
      return null;
    }
  });

  session.defaultSession.setDisplayMediaRequestHandler((request, callback) => {
    desktopCapturer.getSources({ types: ['screen'] }).then((sources) => {
      let targetSource = sources[0];

      try {
        const activeWin = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
        if (activeWin && screen) {
          const currentDisplay = screen.getDisplayMatching(activeWin.getBounds());
          const currentDisplayId = currentDisplay.id.toString();
          const matchingDisplay = sources.find(
            (s) => s.display_id === currentDisplayId || s.id.endsWith(`:${currentDisplayId}`)
          );
          if (matchingDisplay) {
            targetSource = matchingDisplay;
          }
        }
      } catch (e) {
        console.warn('Active monitor detection error:', e);
      }

      if (targetSource) {
        callback({ video: targetSource, audio: 'loopback' });
      } else {
        callback(null);
      }
    }).catch((err) => {
      console.error('Failed to get desktop sources:', err);
      callback(null);
    });
  });

  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (permission === 'media' || permission === 'display-capture') {
      callback(true);
    } else {
      callback(true);
    }
  });

  session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
    if (permission === 'media' || permission === 'display-capture') {
      return true;
    }
    return true;
  });
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    title: 'Scripture Studio - Look at the Book',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: true,
      contextIsolation: false,
      backgroundThrottling: false
    },
  });

  if (process.env.NODE_ENV === 'development' || !app.isPackaged) {
    mainWindow.loadURL('http://localhost:3000');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

app.whenReady().then(() => {
  setupMediaPermissions();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
