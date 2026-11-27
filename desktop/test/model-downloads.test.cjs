'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { prepareModels, cancelModelDownloads } = require('../runtime.cjs');

test('model setup strips credentials, rejects duplicate runs and releases a cancelled download for retry', async () => {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'jarvis-model-setup-'));
  const key = process.env.OPENAI_API_KEY;
  const fixture = path.join(folder, 'bootstrap_models.py');
  const info = { root: folder, storage: folder, python: process.env.JARVIS_TEST_PYTHON || 'python' };
  try {
    process.env.OPENAI_API_KEY = 'fixture-never-passed-to-download-process';
    await fs.writeFile(fixture, 'import json,os,time\nassert "OPENAI_API_KEY" not in os.environ\nprint(json.dumps({"message":"descargando"}),flush=True)\ntime.sleep(20)\n');
    let received;
    const progress = new Promise(resolve => { received = resolve; });
    const first = prepareModels(info, received);
    const cancelled = assert.rejects(first, /interrumpió/);
    await progress;
    await assert.rejects(prepareModels(info, () => {}), /ya está en curso/);
    cancelModelDownloads();
    await cancelled;
    await fs.writeFile(fixture, 'import json,os\nassert "OPENAI_API_KEY" not in os.environ\nprint(json.dumps({"message":"verificado"}),flush=True)\n');
    const messages = [];
    await prepareModels(info, message => messages.push(message));
    assert.deepEqual(messages, ['verificado']);
  } finally {
    cancelModelDownloads();
    if (key === undefined) delete process.env.OPENAI_API_KEY; else process.env.OPENAI_API_KEY = key;
    assert.equal(path.dirname(folder), path.resolve(os.tmpdir()));
    assert.ok(path.basename(folder).startsWith('jarvis-model-setup-'));
    await fs.rm(folder, { recursive: true, force: true });
  }
});
