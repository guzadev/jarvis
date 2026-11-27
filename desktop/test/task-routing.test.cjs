'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
test('a rejected task never reports started or polls a nonexistent job',async()=>{
  const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
  const source=html.slice(html.indexOf('async function launchTask('),html.indexOf('async function pollTask('));
  for(const response of [{ok:false,json:async()=>({detail:'Motor no disponible'})},{ok:true,json:async()=>({status:'error'})}]){
    const outputs=[],cards=[];
    const c={window:{JarvisRealtimeOwned:{turn:1},JarvisMissions:{selectedProject:'fixture'},dispatchEvent(){throw new Error('Unexpected mission notification');}},dc:{},
      apiFetch:async()=>response,toolOutput(_id,result){outputs.push(result);},addTaskCard(id){cards.push(id);},pollTask(){throw new Error('Unexpected polling');}};
    vm.createContext(c);vm.runInContext(source,c);await c.launchTask('test-call','Prueba','Crear archivo');
    assert.equal(outputs.length,1);assert.equal(outputs[0].status,'error');assert.equal(cards.length,0);
  }
});
