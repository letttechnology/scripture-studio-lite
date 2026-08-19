#!/usr/bin/env node
// Cross-platform port killer for VS Code preLaunchTasks (win32 / macOS / Linux).
// Usage: node kill-port.mjs <port>
// Kills whatever LISTENs on <port>, then waits until the port is actually free
// (up to 10s) so the relaunched service never races the dying one.
// Always exits 0 — a free port is success, not an error.

import { execSync } from 'node:child_process';
import net from 'node:net';

const port = String(parseInt(process.argv[2], 10));
if (port === 'NaN') {
  console.error('usage: node kill-port.mjs <port>');
  process.exit(0);
}

// Full paths so the script never depends on PATH (minimal shells, CI, etc.)
const SYS32 = process.platform === 'win32'
  ? `${process.env.SystemRoot || 'C:\\Windows'}\\System32\\`
  : '';

function listeningPids() {
  const pids = new Set();
  try {
    if (process.platform === 'win32') {
      const out = execSync(`"${SYS32}netstat.exe" -ano -p tcp`, { encoding: 'utf8' });
      for (const line of out.split('\n')) {
        const m = line.trim().match(/^TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)/i);
        if (m && m[1] === port) pids.add(m[2]);
      }
    } else {
      const out = execSync(`lsof -ti tcp:${port} -sTCP:LISTEN`, { encoding: 'utf8' });
      for (const pid of out.split('\n')) if (pid.trim()) pids.add(pid.trim());
    }
  } catch { /* no listener → empty set */ }
  return pids;
}

function kill(pid) {
  try {
    if (process.platform === 'win32') execSync(`"${SYS32}taskkill.exe" /F /PID ${pid}`, { stdio: 'ignore' });
    else process.kill(Number(pid), 'SIGKILL');
  } catch { /* already gone */ }
}

function portFree() {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => resolve(false));
    srv.once('listening', () => srv.close(() => resolve(true)));
    srv.listen(Number(port), '0.0.0.0');
  });
}

const pids = listeningPids();
for (const pid of pids) {
  console.log(`kill-port: stopping pid ${pid} on port ${port}`);
  kill(pid);
}

const deadline = Date.now() + 10_000;
while (!(await portFree())) {
  if (Date.now() > deadline) {
    console.error(`kill-port: port ${port} still busy after 10s`);
    break;
  }
  await new Promise((r) => setTimeout(r, 200));
}
process.exit(0);
