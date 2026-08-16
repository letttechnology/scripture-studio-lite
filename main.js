const { app, BrowserWindow, session, desktopCapturer, screen } = require('electron');
const path = require('path');

function setupMediaPermissions() {
  if (!session.defaultSession) return;

  session.defaultSession.setDisplayMediaRequestHandler((request, callback) => {
    desktopCapturer.getSources({ types: ['screen', 'window'] }).then((sources) => {
      let targetSource = sources[0];

      try {
        const activeWin = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
        if (activeWin) {
          const winMediaSourceId = typeof activeWin.getMediaSourceId === 'function' ? activeWin.getMediaSourceId() : null;
          const matchingWindow = sources.find(
            (s) => (winMediaSourceId && s.id === winMediaSourceId) ||
                   (s.id.startsWith('window:') && s.name && s.name.includes('Scripture Studio'))
          );
          if (matchingWindow) {
            targetSource = matchingWindow;
          } else if (screen) {
            const currentDisplay = screen.getDisplayMatching(activeWin.getBounds());
            const matchingDisplay = sources.find(
              (s) => s.display_id === currentDisplay.id.toString() || s.id.includes(currentDisplay.id.toString())
            );
            if (matchingDisplay) {
              targetSource = matchingDisplay;
            }
          }
        }
      } catch (e) {
        console.warn('Active window/monitor detection error:', e);
      }

      if (targetSource) {
        callback({ video: targetSource });
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
  const win = new BrowserWindow({
    width: 1366,
    height: 900,
    title: 'Scripture Studio LITE',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      webviewTag: true
    }
  });

  win.loadFile(path.join(__dirname, 'index.html'));
}

app.whenReady().then(() => {
  setupMediaPermissions();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
