'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { prepareBundled, inspect } = require('../runtime.cjs');
test('first launch relocates its own runtimes and preserves settings and encrypted credentials', async () => {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'jarvis-desktop-runtime-'));
  try {
    const root = path.join(temporary, 'backend'), home = path.join(temporary, 'runtime', 'python');
    await fs.mkdir(home, { recursive: true }); await fs.writeFile(path.join(home, 'python.exe'), 'fixture');
    const envs = [path.join(root, '.venv'), path.join(temporary, 'data', '.agent-venv'), path.join(temporary, 'data', '.owned-voice-venv')];
    for (const env of envs) { await fs.mkdir(path.join(env, 'Scripts'), { recursive: true }); await fs.writeFile(path.join(env, 'Scripts', 'python.exe'), 'fixture'); }
    await prepareBundled(root, home);
    const first = await inspect(root);
    assert.equal(first.storage, path.join(temporary, 'data')); assert.equal(first.settings.voice, 'owned'); assert.equal(first.pythonHome, home);
    assert.equal(first.keyConfigured, false);
    assert.equal(first.settings.conversation_provider,'openai');
    for (const env of envs) assert.match(await fs.readFile(path.join(env, 'pyvenv.cfg'), 'utf8'), /version = 3\.13\.3/);
    assert.deepEqual(JSON.parse(await fs.readFile(path.join(root, '.wake-config.json'))), { enabled: false, microphone: 'auto' });
    const changed = { ...first.settings, max_turns: 7 };
    await fs.writeFile(path.join(root, '.jarvis-app.json'), JSON.stringify(changed));
    await fs.writeFile(path.join(root, '.jarvis-openai.dpapi'), Buffer.from([1, 5, 9]));
    await prepareBundled(root, home);
    assert.deepEqual((await inspect(root)).settings, changed);
    assert.deepEqual(await fs.readFile(path.join(root, '.jarvis-openai.dpapi')), Buffer.from([1, 5, 9]));
  } finally {
    assert.equal(path.dirname(temporary), path.resolve(os.tmpdir()));
    assert.ok(path.basename(temporary).startsWith('jarvis-desktop-runtime-'));
    await fs.rm(temporary, { recursive: true, force: true });
  }
});
