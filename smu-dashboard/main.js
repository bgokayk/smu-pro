const { app, BrowserWindow, ipcMain, shell } = require('electron')
const path = require('path')
const fs = require('fs')
const { exec } = require('child_process')

// content-ops root is one level up from this file
const CONTENT_OPS = path.join(__dirname, '..')

function readJson(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8')
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function getIstanbulDate() {
  const now = new Date()
  // UTC+3 offset
  const istanbul = new Date(now.getTime() + 3 * 60 * 60 * 1000)
  return istanbul.toISOString().slice(0, 10)
}

// Find the most relevant schedule: today (if it has future slots), then next upcoming, then latest
function findSchedule(today) {
  const schedDir = path.join(CONTENT_OPS, 'schedules')
  const nowLocal = new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString().slice(0, 16).replace('T', ' ')

  // Check today's schedule first — if it has future slots, use it
  const todayFile = path.join(schedDir, `${today}_smu_schedule.json`)
  if (fs.existsSync(todayFile)) {
    const data = readJson(todayFile)
    const hasFuture = data && (data.slots || []).some(s =>
      (s.status === 'scheduled' || s.status === 'needs_queue_item') &&
      s.publishAtLocal >= nowLocal
    )
    if (hasFuture) return data
  }

  // Look for upcoming schedule files (today or later)
  try {
    const files = fs.readdirSync(schedDir)
      .filter(f => f.endsWith('_smu_schedule.json'))
      .sort()
    // Prefer the earliest file >= today that has future slots
    for (const f of files) {
      const date = f.replace('_smu_schedule.json', '')
      if (date >= today) {
        const data = readJson(path.join(schedDir, f))
        if (data && (data.slots || []).some(s => s.publishAtLocal >= nowLocal)) return data
      }
    }
    // Fallback: latest file
    if (files.length === 0) return null
    return readJson(path.join(schedDir, files[files.length - 1]))
  } catch {
    return null
  }
}

// Find comment drafts for today
function findCommentDrafts(today) {
  const commentsDir = path.join(CONTENT_OPS, 'comments')
  const todayFile = path.join(commentsDir, `${today}_comment_drafts.json`)
  if (fs.existsSync(todayFile)) return readJson(todayFile)

  try {
    const files = fs.readdirSync(commentsDir)
      .filter(f => f.endsWith('_comment_drafts.json'))
      .sort()
    if (files.length === 0) return null
    return readJson(path.join(commentsDir, files[files.length - 1]))
  } catch {
    return null
  }
}

ipcMain.handle('get-data', () => {
  const today = getIstanbulDate()

  const config = readJson(path.join(CONTENT_OPS, 'smu_config.json'))
  const daemonState = readJson(path.join(CONTENT_OPS, 'state', 'daemon_state.json'))
  const pipelineState = readJson(path.join(CONTENT_OPS, 'state', 'pipeline_state.json'))
  const schedule = findSchedule(today)
  const helpQueue = readJson(path.join(CONTENT_OPS, 'state', 'needs_help.json')) || []
  const commentDrafts = findCommentDrafts(today)

  return {
    today,
    nowUtc: new Date().toISOString(),
    config,
    daemonState,
    pipelineState,
    schedule,
    helpQueue,
    commentDrafts,
  }
})

ipcMain.handle('run-command', async (event, cmd) => {
  return new Promise((resolve) => {
    const cwd = CONTENT_OPS
    exec(cmd, { cwd, timeout: 30000 }, (err, stdout, stderr) => {
      resolve({ ok: !err, stdout, stderr, error: err ? err.message : null })
    })
  })
})

ipcMain.handle('open-folder', (event, folderPath) => {
  shell.openPath(folderPath)
})

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 960,
    minHeight: 680,
    backgroundColor: '#0a0a0a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    title: 'SMU Dashboard',
    show: false,
  })

  win.loadFile(path.join(__dirname, 'index.html'))

  win.once('ready-to-show', () => {
    win.show()
  })

  // Open devtools in dev mode
  if (process.env.SMU_DEV) {
    win.webContents.openDevTools()
  }
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  app.quit()
})
