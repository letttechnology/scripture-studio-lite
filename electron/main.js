const { app, BrowserWindow, session, desktopCapturer, screen } = require('electron');
const path = require('path');

function setupMediaPermissions() {
  if (!session.defaultSession) return;

  session.defaultSession.setDisplayMediaRequestHandler((request, callback) => {
    desktopCapturer.getSources({ types: ['screen', 'window'] }).then((sources) => {
      let targetSource = sources[0];

      try {
        const activeWin = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
        if (activeWin && screen) {
          const currentDisplay = screen.getDisplayMatching(activeWin.getBounds());
          const matchingSource = sources.find(
            (s) => s.display_id === currentDisplay.id.toString() || s.id.includes(currentDisplay.id.toString())
          );
          if (matchingSource) {
            targetSource = matchingSource;
          }
        }
      } catch (e) {
        console.warn('Active monitor detection error:', e);
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
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    title: 'Scripture Studio - Look at the Book',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
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
