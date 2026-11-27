import { createHash } from 'node:crypto';
import { lstat, readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { deflateRawSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const mathManifest=JSON.parse(await readFile(join(root,'public/assets/vendor/vendor-math-files.json'),'utf8'));
const mathAssets=mathManifest.files.map(item=>item.path);
if(mathAssets.some(path=>!/^assets\/vendor\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+$/.test(path)||path.split('/').some(part=>part==='..')))throw new Error('Ruta de biblioteca matemÃ¡tica incorrecta.');
export const publicAssets = ['assets/integrations.css','assets/integrations.js','assets/data-results.css','assets/data-results.js','assets/missions.css', 'assets/missions.js', 'assets/local-models.css', 'assets/local-models.js', 'assets/local-voice.js', 'assets/realtime-owned.js', 'assets/molecular-orb.js', 'assets/pc-connection.js',
  'assets/vendor/vendor-math-files.json',...mathAssets,
  ...['marked.min.js','purify.min.js','apexcharts.min.js','gridjs.umd.js','gridjs-mermaid.min.css','fonts.css','manifest.json',
      'font-0.woff2','font-1.woff2','font-2.woff2','font-3.woff2','font-4.woff2'].map(name=>'assets/vendor/'+name)];
const sources = `
ABRIR_JARVIS_ONLINE.cmd ACTIVAR_INICIO_AUTOMATICO.cmd ACTUALIZAR_JARVIS.cmd
CONECTAR_CLAUDE.cmd DESACTIVAR_INICIO_AUTOMATICO.cmd DETENER_JARVIS.cmd
INICIAR_JARVIS.cmd INSTALAR_JARVIS.cmd LICENSE LEEME-COMPANERO.md
actualizar.ps1 agent_store.py agent_worker.py office_actions.py app_api.py app_runtime.py
bootstrap_models.py local_models.py whisper-weights.json
data_tools.py data_credentials.py public_reader.py requirements-data.txt voice_diagnostics.py
integration_store.py integration_http.py integrations.py
conectar-claude.ps1 execution_review.py index.html inicio-automatico.ps1
fish_voice.py owned_voice.py owned_voice_service.py preparar-voz-propia.py requirements-owned-voice.txt
qwen_voice_service.py preparar-voz-qwen.py requirements-qwen.txt requirements-qwen-fast.txt qwen-voice-weights.json
instalar-jarvis.ps1 jarvis.ps1 local_voice_service.py mission_manager.py
preparar-activacion.py preparar-modelos.py requirements-agent.txt requirements.txt
reviewed_process.py science_worker.py server.py speech_worker.py wake_word.py windows_audio.py
wake_transcriber.py whisper_wake.py web_search_worker.py
`.trim().split(/\s+/);
const sum = bytes => createHash('sha256').update(bytes).digest('hex');
const crcTable = Array.from({length:256}, (_,n) => {
  for (let bit=0;bit<8;bit++) n=(n&1) ? (0xedb88320^(n>>>1)) : (n>>>1);
  return n>>>0;
});
function crc32(bytes) {
  let crc=0xffffffff;
  for (const b of bytes) crc=crcTable[(crc^b)&255]^(crc>>>8);
  return (crc^0xffffffff)>>>0;
}
// ZIP32 with fixed timestamps, UTF-8 entry names, raw DEFLATE and no extras.
function archive(files) {
  const entries=[], central=[];
  let offset=0;
  for (const [path, bytes] of files) {
    const name=Buffer.from(path), packed=deflateRawSync(bytes), local=Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50); local.writeUInt16LE(20,4);
    local.writeUInt16LE(0x800,6); local.writeUInt16LE(8,8); local.writeUInt16LE(33,12);
    local.writeUInt32LE(crc32(bytes),14); local.writeUInt32LE(packed.length,18);
    local.writeUInt32LE(bytes.length,22); local.writeUInt16LE(name.length,26);
    const header=Buffer.alloc(46);
    header.writeUInt32LE(0x02014b50); header.writeUInt16LE(20,4);
    local.copy(header,6,4,28); header.writeUInt32LE(offset,42);
    entries.push(local,name,packed); central.push(header,name);
    offset+=local.length+name.length+packed.length;
  }
  const directory=Buffer.concat(central), end=Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50); end.writeUInt16LE(files.length,8);
  end.writeUInt16LE(files.length,10); end.writeUInt32LE(directory.length,12); end.writeUInt32LE(offset,16);
  return Buffer.concat([...entries,directory,end]);
}

export async function packageCompanion(destination) {
  const files=[];
  for (const path of [...sources,...publicAssets.map(p=>'public/'+p)].sort()) {
    const source=join(root,path);
    if (!(await lstat(source)).isFile()) throw new Error('Se requiere un archivo regular: '+path);
    files.push([path,await readFile(source)]);
  }
  const hashes=Object.fromEntries(files.map(([path,bytes])=>[path,sum(bytes)]));
  const version=sum(JSON.stringify(hashes)).slice(0,16);
  files.push(['companion-files.json',Buffer.from(JSON.stringify({version,files:hashes},null,2))]);
  const zip=archive(files), filename='Jarvis-Codigo-Windows.zip';
  await mkdir(destination,{recursive:true});
  await writeFile(join(destination,filename),zip);
  await writeFile(join(destination,'version.json'),JSON.stringify({version,filename,sha256:sum(zip),bytes:zip.length},null,2));
}
if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  await packageCompanion(resolve(process.argv[2] || join(root,'public/downloads')));
}
