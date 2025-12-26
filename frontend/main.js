const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');
const fs = require('fs');

let mainWindow;
let pythonProcess;
const PYTHON_PORT = 12345;

// --- Config ---
// Adjust python command if needed (e.g. 'python3' on Mac/Linux)
let PYTHON_CMD = process.platform === 'win32' ? 'python' : 'python3';
const SERVER_SCRIPT = path.join(__dirname, '../backend/server.py');

// Attempt to use venv python if available (more reliable)
const VENV_PYTHON = path.join(__dirname, '../backend/venv/Scripts/python.exe');
if (process.platform === 'win32' && fs.existsSync(VENV_PYTHON)) {
    console.log("Using Virtual Environment Python:", VENV_PYTHON);
    PYTHON_CMD = VENV_PYTHON;
}

function createWindow() {
  const iconPath = path.join(__dirname, 'assets/Syntaxripper.ico');
  
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    backgroundColor: '#1a1a1a',
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
    show: false
  });

  mainWindow.setMenuBarVisibility(false); // Remove standard menu bar

  mainWindow.loadFile('index.html');
  
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Check for updates
  autoUpdater.checkForUpdatesAndNotify();
}

function startPythonServer() {
  console.log('Starting Python Server...');
  console.log('Script Path:', SERVER_SCRIPT);

  // Pass PID so Python can monitor us
  pythonProcess = spawn(PYTHON_CMD, [SERVER_SCRIPT, process.pid], {
    cwd: path.dirname(SERVER_SCRIPT)
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python]: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Err]: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
  });
}

function killPythonServer() {
  if (pythonProcess) {
    console.log('Killing Python Server...');
    const pid = pythonProcess.pid;
    pythonProcess = null; // Prevent re-entry

    if (process.platform === 'win32') {
        // Windows: Force kill process tree SYNC to ensure it happens before exit
        try {
            require('child_process').execSync(`taskkill /pid ${pid} /T /F`);
        } catch (e) {
            // Process might be already dead, ignore
        }
    } else {
        // Unix: Standard kill
        try {
            process.kill(pid, 'SIGKILL');
        } catch(e) { /* ignore */ }
    }
  }
}

app.on('ready', () => {
  startPythonServer();
  createWindow();
});

app.on('window-all-closed', () => {
  killPythonServer();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  killPythonServer();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// Auto-Updater Events
autoUpdater.on('update-available', () => {
  mainWindow.webContents.send('update_available');
});

autoUpdater.on('update-downloaded', () => {
  mainWindow.webContents.send('update_downloaded');
});

ipcMain.on('restart_app', () => {
  console.log("Restarting application...");
  app.relaunch();
  app.exit(0);
});

// Folder Selection Dialog
ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  if (result.canceled) return null;
  return result.filePaths[0];
});

// File Selection Dialog
ipcMain.handle('select-file', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    ...options
  });
  if (result.canceled) return null;
  return result.filePaths[0];
});
