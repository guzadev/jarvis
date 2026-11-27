'use strict';
const path = require('node:path');
const APP_ORIGIN = 'http://127.0.0.1:8788';
function localURL(value) {
  try { const url = new URL(value); return url.origin === APP_ORIGIN && !url.username && !url.password; }
  catch { return false; }
}
function externalURL(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password &&
      !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
  } catch { return false; }
}
function audioPermission(contents, permission, details, mainContents) {
  if (!mainContents || contents !== mainContents || mainContents.isDestroyed() || !localURL(mainContents.getURL())) return false;
  if (permission !== 'media' || details.isMainFrame === false) return false;
  if (!localURL(details.requestingUrl || details.securityOrigin || details.requestingOrigin || '')) return false;
  const media = details.mediaTypes || (details.mediaType ? [details.mediaType] : []);
  return media.length > 0 && media.every(kind => kind === 'audio');
}
function normalizePath(value) { return path.win32.resolve(value).replaceAll('/', '\\').toLowerCase(); }
function ownedListener(processInfo, root, pythonHome) {
  if (!processInfo || !Number.isInteger(processInfo.ProcessId)) return false;
  const python = normalizePath(path.join(root, '.venv', 'Scripts', 'python.exe'));
  const command = [...String(processInfo.CommandLine || '').matchAll(/"([^"]*)"|(\S+)/g)].map(match => match[1] ?? match[2]);
  const script = normalizePath(path.join(root, 'server.py'));
  const actual = normalizePath(processInfo.ExecutablePath || '.');
  const executableMatches = actual === python || (pythonHome && actual === normalizePath(path.join(pythonHome, 'python.exe')));
  return Boolean(executableMatches && command.length === 3 && normalizePath(command[0]) === python && command[1] === '-u' && normalizePath(command[2]) === script);
}
module.exports = { APP_ORIGIN, localURL, externalURL, audioPermission, ownedListener };
