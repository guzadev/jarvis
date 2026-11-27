import { cp, mkdir, mkdtemp, rename, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { packageCompanion, publicAssets } from './package-companion.mjs';
const root=resolve(import.meta.dirname,'..');
const output=join(root,'.web-output');
const stage=await mkdtemp(join(root,'.web-build-'));
try {
  await mkdir(join(stage,'assets'));
  for (const name of ['index.html','LICENSE']) await cp(join(root,name),join(stage,name));
  for (const name of publicAssets) await cp(join(root,'public',name),join(stage,name));
  await packageCompanion(join(stage,'downloads'));
  if (resolve(output)!==join(root,'.web-output')) throw new Error('Destino incorrecto');
  await rm(output,{recursive:true,force:true});
  await rename(stage,output);
  console.log('Interfaz y compañero Windows preparados.');
} finally {
  if (stage.startsWith(join(root,'.web-build-'))) await rm(stage,{recursive:true,force:true});
}
