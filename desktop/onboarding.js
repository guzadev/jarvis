'use strict';
const $ = id => document.getElementById(id);
function render(state) {
  $('message').textContent = state.message;
  $('progress').hidden = !state.busy;
  $('connect').hidden = !state.needsKey;
  $('error').hidden = !state.error; $('error').textContent = state.error || '';
  $('recovery').hidden = !state.error;
  $('connect').querySelector('button').disabled = Boolean(state.busy);
}
window.jarvisSetup.onStatus(render);
window.jarvisSetup.status().then(render);
$('connect').addEventListener('submit', async event => {
  event.preventDefault(); const key = $('key').value; $('key').value = '';
  await window.jarvisSetup.connect(key);
});
$('retry').addEventListener('click', () => window.jarvisSetup.retry());
$('diagnostics').addEventListener('click', () => window.jarvisSetup.diagnostics());
