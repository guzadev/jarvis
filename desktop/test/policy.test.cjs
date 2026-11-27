'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { localURL, externalURL, audioPermission, ownedListener, APP_ORIGIN } = require('../policy.cjs');
test('only exact loopback origin is privileged', () => {
  assert.equal(localURL(APP_ORIGIN + '/'), true);
  for (const url of ['http://127.0.0.1:8789/', 'https://127.0.0.1:8788/', 'http://127.0.0.1.evil.test:8788/', 'file:///index.html', 'http://user:pass@127.0.0.1:8788/']) assert.equal(localURL(url), false);
});
test('external URLs never launch native schemes or credentials', () => {
  assert.equal(externalURL('https://example.org/report'), true);
  for (const url of ['file:///C:/secret', 'cmd.exe', 'javascript:alert(1)', 'ms-settings:privacy-microphone', 'http://localhost:8788', 'https://user:pass@example.org/']) assert.equal(externalURL(url), false);
});
test('microphone restricted to own main document and audio', () => {
  const own = { getURL: () => APP_ORIGIN + '/', isDestroyed: () => false };
  const request = { requestingUrl: APP_ORIGIN + '/', isMainFrame: true, mediaTypes: ['audio'] };
  assert.equal(audioPermission(own, 'media', request, own), true);
  for (const details of [{ ...request, isMainFrame: false }, { ...request, mediaTypes: ['video'] }, { ...request, mediaTypes: ['audio', 'video'] }, { ...request, requestingUrl: 'https://evil.test/' }, { ...request, mediaTypes: [] }]) assert.equal(audioPermission(own, 'media', details, own), false);
  assert.equal(audioPermission({}, 'media', request, own), false);
  assert.equal(audioPermission(own, 'display-capture', request, own), false);
});
test('an occupied port is trusted only for the exact registered Python and server', () => {
  const root = 'E:\\Apps\\Jarvis\\backend';
  const process = { ProcessId: 1234, ExecutablePath: root + '\\.venv\\Scripts\\python.exe', CommandLine: '"' + root + '\\.venv\\Scripts\\python.exe" -u "' + root + '\\server.py"' };
  assert.equal(ownedListener(process, root), true);
  const baseHome = 'E:\\Apps\\Jarvis\\runtime\\python';
  assert.equal(ownedListener({ ...process, ExecutablePath: baseHome + '\\python.exe' }, root, baseHome), true);
  assert.equal(ownedListener({ ...process, ExecutablePath: 'C:\\Other\\python.exe' }, root), false);
  assert.equal(ownedListener({ ...process, CommandLine: 'python fake-server.py' }, root), false);
  assert.equal(ownedListener({ ...process, CommandLine: process.CommandLine.replace('server.py', 'server.py.evil') }, root), false);
  assert.equal(ownedListener({ ...process, CommandLine: '"C:\\Other\\python.exe" -u "' + root + '\\server.py"' }, root), false);
  assert.equal(ownedListener({ ...process, CommandLine: process.CommandLine + ' -c evil' }, root), false);
  assert.equal(ownedListener(null, root), false);
});
