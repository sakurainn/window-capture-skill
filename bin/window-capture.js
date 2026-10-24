#!/usr/bin/env node
'use strict';

const { spawn } = require('node:child_process');
const path = require('node:path');

const script = path.join(__dirname, '..', 'scripts', 'screen_fetch.py');
const args = process.argv.slice(2);

const candidates = [];
if (process.env.WINDOW_CAPTURE_PYTHON) {
  candidates.push([process.env.WINDOW_CAPTURE_PYTHON, []]);
}
if (process.platform === 'win32') {
  candidates.push(['python', []], ['py', ['-3']]);
} else {
  candidates.push(['python3', []], ['python', []]);
}

const env = {
  ...process.env,
  PYTHONUTF8: process.env.PYTHONUTF8 || '1',
  PYTHONIOENCODING: process.env.PYTHONIOENCODING || 'utf-8',
};

function run(index) {
  const [command, prefix] = candidates[index];
  const child = spawn(command, [...prefix, script, ...args], {
    stdio: 'inherit',
    env,
  });

  child.once('error', (err) => {
    if (err.code === 'ENOENT' && index + 1 < candidates.length) {
      run(index + 1);
      return;
    }
    if (err.code === 'ENOENT') {
      console.error(
        'window-capture-skill: 找不到 Python 3，请先安装 Python，或用 WINDOW_CAPTURE_PYTHON 指定解释器路径。'
      );
    } else {
      console.error(`window-capture-skill: 启动 ${command} 失败：${err.message}`);
    }
    process.exit(127);
  });

  child.once('exit', (code, signal) => {
    if (signal) {
      try {
        process.kill(process.pid, signal);
      } catch {
        process.exit(1);
      }
      return;
    }
    process.exit(code === null ? 1 : code);
  });
}

run(0);
