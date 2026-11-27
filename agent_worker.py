"""One OpenJarvis mission process; JSON events on stdout, no secret output."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

def emit(kind,**data):
    print(json.dumps({'type':kind,**data},ensure_ascii=False),flush=True)

def run(job):
    from openjarvis.agents.orchestrator import OrchestratorAgent
    from openjarvis.agents._stubs import AgentContext
    from openjarvis.core.types import Conversation,Message,Role,ToolResult
    from openjarvis.tools._stubs import BaseTool,ToolSpec
    from openjarvis.tools.file_read import FileReadTool
    from openjarvis.tools.file_write import FileWriteTool
    from openjarvis.tools.web_search import WebSearchTool
    import agent_store
    workspace=Path(job['workspace']).resolve();workspace.mkdir(parents=True,exist_ok=True)
    os.chdir(workspace)
    provider=job['provider']
    if provider=='claude':
        class ClaudeReasoner:
            engine_id='claude_code_reasoner';is_cloud=True
            def generate(self,messages,**kwargs):
                prompt='\n\n'.join(message.role.value.upper()+':\n'+message.text for message in messages)
                import app_runtime
                private=Path(app_runtime.settings()['storage_dir'])/'private/claude-reasoner'
                private.mkdir(parents=True,exist_ok=True)
                env=os.environ.copy();env.pop('CLAUDE_CODE_SIMPLE',None)
                env.update(CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',CLAUDE_CODE_DISABLE_AUTO_MEMORY='1')
                process=subprocess.run([job['claude_command'],'-p','--tools','','--strict-mcp-config',
                                        '--mcp-config','{"mcpServers":{}}','--disable-slash-commands','--no-session-persistence',
                                        '--setting-sources','','--settings','{"disableAllHooks":true}', '--output-format','json'],
                                       input=prompt,capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=private,env=env,
                                       creationflags=subprocess.CREATE_NO_WINDOW,timeout=job['timeout'])
                try:response=json.loads(process.stdout)
                except ValueError:raise RuntimeError('Claude Code no devolvió una respuesta válida. Verificá su conexión.')
                if process.returncode or response.get('is_error'):raise RuntimeError(response.get('result','Claude Code no pudo completar el pedido.')[:1800])
                return {'content':response.get('result',''),'usage':response.get('usage',{}),'finish_reason':'stop'}
        engine=ClaudeReasoner()
    elif provider=='local':
        from openjarvis.engine.ollama import OllamaEngine
        from openjarvis.engine._base import EngineConnectionError
        import httpx
        class LocalReasoner(OllamaEngine):
            def generate(self,messages,**kwargs):
                loaded=False
                try:
                    state=httpx.get(job['ollama_url']+'/api/ps',timeout=2,trust_env=False).json()
                    loaded=any(item.get('name')==job['model'] for item in state.get('models',[]))
                except (httpx.HTTPError,ValueError):pass
                self._client.timeout=httpx.Timeout(180 if loaded else 300,connect=5)
                emit('progress',message=('Preparando la respuesta con '+job['model'] if loaded else
                     'Cargando '+job['model']+' en tu PC. El primer inicio tarda más que las siguientes respuestas.'))
                try:return super().generate(messages,**kwargs)
                except EngineConnectionError as error:
                    raise RuntimeError('El motor local tardó demasiado en responder o perdió la conexión. Podés volver a intentar tu pedido.') from error
        engine=LocalReasoner(host=job['ollama_url'],timeout=180)
        engine._client.close()
        engine._client=httpx.Client(base_url=job['ollama_url'],timeout=180,trust_env=False)
        os.environ.pop('OPENAI_API_KEY',None);os.environ.pop('ANTHROPIC_API_KEY',None)
    else:
        from openjarvis.engine.cloud import CloudEngine
        engine=CloudEngine()

    class FunctionTool(BaseTool):
        def __init__(self,name,description,parameters,function):
            self.tool_id=name;self._spec=ToolSpec(name=name,description=description,parameters=parameters,timeout_seconds=180)
            self.function=function
        @property
        def spec(self):return self._spec
        def execute(self,**parameters):
            try:
                value=self.function(**parameters)
                success=not (isinstance(value,dict) and (value.get('status')=='error' or ('exit_code' in value and value['exit_code']!=0)))
                return ToolResult(tool_name=self.tool_id,content=json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value,success=success)
            except Exception as error:
                return ToolResult(tool_name=self.tool_id,content=str(error),success=False)

    def schema(properties,required=None):return {'type':'object','properties':properties,'required':required or list(properties)}
    string={'type':'string'}
    def execute_python(code):
        import execution_review
        approval,payload=execution_review.propose(job,'Python',code,emit)
        code=payload['content']
        folder=workspace/'.jarvis-runs';folder.mkdir(exist_ok=True)
        script=folder/(str(time.time_ns())+'.py');script.write_text(code,encoding='utf-8')
        clean={key:value for key,value in os.environ.items() if not any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD'))}
        clean['MPLBACKEND']='Agg'
        return reviewed_process(approval,[sys.executable,str(script)],clean,120)
    def shell(command):
        import execution_review
        approval,payload=execution_review.propose(job,'PowerShell',command,emit)
        command=payload['content']
        clean={key:value for key,value in os.environ.items() if not any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD'))}
        return reviewed_process(approval,['powershell.exe','-NoProfile','-NonInteractive','-Command',command],clean,180)
    def reviewed_process(approval,command,env,timeout):
        from reviewed_process import execute
        try:
            value=execute(command,workspace,env,timeout)
        except Exception as error:
            agent_store.approval_transition(approval,'executing','failed',str(error)[:1000]);raise
        agent_store.approval_transition(approval,'executing','done' if value['exit_code']==0 else 'failed',json.dumps(value,ensure_ascii=False))
        return value
    def science(**parameters):
        parameters['workspace']=str(workspace)
        result=subprocess.run([sys.executable,str(ROOT/'science_worker.py')],input=json.dumps(parameters,ensure_ascii=False),
                              capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=workspace,
                              creationflags=subprocess.CREATE_NO_WINDOW,timeout=40)
        if result.returncode:raise ValueError(result.stdout[-3000:] or result.stderr[-1000:])
        return json.loads(result.stdout)
    def files(path='.'):
        target=(workspace/path).resolve()
        if not target.is_relative_to(workspace):raise ValueError('La ruta debe estar dentro del proyecto.')
        return [{'name':item.name,'directory':item.is_dir()} for item in list(target.iterdir())[:150]]
    def report():
        import psutil
        return {'date':time.strftime('%Y-%m-%d %H:%M'),'cpu_percent':psutil.cpu_percent(interval=.2),
                'ram_percent':psutil.virtual_memory().percent,'disk_free_gb':round(psutil.disk_usage(str(ROOT.anchor)).free/2**30,2),
                'notes':agent_store.notes(),'recent_missions':[{k:item[k] for k in ('title','status','provider','started')} for item in agent_store.recent(8)]}
    import office_actions
    receipts=[]
    def office(action, **params):
        receipt=action(workspace, **params)
        receipts.append(receipt)
        emit("office_receipt", **receipt)
        return receipt
    opened=[]
    def open_artifact(filename):
        import httpx
        if not any(r["path"]==filename for r in receipts):
            raise ValueError("Elegí un archivo Office creado en esta misión.")
        url="http://127.0.0.1:"+os.environ.get("JARVIS_PORT","8788")+"/api/missions/"+job["id"]+"/open-artifact"
        with httpx.Client(trust_env=False,timeout=5) as client:
            for attempt in range(3):
                response=client.post(url,json={"path":filename})
                if response.status_code!=409 or "comprobante" not in response.text:break
                time.sleep(.1)
        if response.is_error:raise RuntimeError("Windows no aceptó la apertura del archivo.")
        opened.append(filename)
        return response.json()
    def open_web_project(filename):
        import httpx
        response=httpx.post('http://127.0.0.1:'+os.environ.get('JARVIS_PORT','8788')+'/api/projects/'+job.get('project','aurelio')+'/open-web',
                            json={'path':filename},timeout=12,trust_env=False)
        if response.is_error:raise RuntimeError('No pude abrir el HTML del proyecto en el navegador.')
        result=response.json()
        if not result.get('ok'):raise RuntimeError(result.get('error','No pude confirmar la ventana del navegador.'))
        return result
    tools=[FunctionTool("create_spreadsheet","Creá y verificá una planilla Excel XLSX con encabezados y filas de datos.",schema({"filename":string,"headers":{"type":"array","items":string},"rows":{"type":"array","items":{"type":"array","items":{}}}}),lambda **p:office(office_actions.create_spreadsheet, **p)),
           FunctionTool("open_artifact","Solicitá abrir un documento creado en esta misión, sólo cuando el usuario lo pida.",schema({"filename":string}),open_artifact),
           FunctionTool('open_web_project','Abrí y ejecutá un archivo HTML de este proyecto en una ventana visible del navegador. Si piden crear una calculadora, juego o app web y abrirla, escribí el HTML y después llamá esta herramienta. No requiere comandos ni instalar dependencias.',schema({'filename':string}),open_web_project),
           FunctionTool("create_document","Creá y verificá un documento Word DOCX con título y párrafos.",schema({"filename":string,"title":string,"paragraphs":{"type":"array","items":string}}),lambda **p:office(office_actions.create_document, **p)),
           FunctionTool('calculator','Calculá una expresión matemática numérica con límites de memoria y tiempo.',schema({'expression':string}),lambda expression:science(operation='simplify',expression=expression)),FileReadTool(allowed_dirs=[str(workspace)]),FileWriteTool(allowed_dirs=[str(workspace)]),
           WebSearchTool(engine='duckduckgo'),
           FunctionTool('science','Calculá o graficá expresiones matemáticas de forma automática, con SymPy. solve resuelve expresión=0; plot guarda PNG; se admiten Eq, sin, cos, sqrt, exp, log y pi.',schema({'operation':{'type':'string','enum':['solve','simplify','differentiate','integrate','plot']},'expression':string,'variable':string,'lower':{'type':'number'},'upper':{'type':'number'},'filename':string},['operation','expression']),science),
           FunctionTool('run_python','Prepará un programa Python general para ejecutar después de que el usuario revise y apruebe sus bytes exactos. Para matemática normal preferí science, que es automático.',schema({'code':string}),execute_python),
           FunctionTool('run_command','Proponé un lote PowerShell para construir y verificar un proyecto: Node/npm/git. El usuario revisará el comando exacto antes de ejecutarlo.',schema({'command':string}),shell),
           FunctionTool('list_files','Listá archivos de una carpeta del proyecto.',schema({'path':string}),files),
           FunctionTool('remember','Guardá un dato que el usuario quiera recordar para las próximas conversaciones.',schema({'content':string}),lambda content:{'id':agent_store.note_add(content)}),
           FunctionTool('recall','Consultá la memoria persistente del usuario.',schema({},[]),agent_store.notes),
           FunctionTool('system_report','Consultá datos reales de esta PC, notas y trabajos recientes para un informe.',schema({},[]),report),
           FunctionTool('open_app','Abrí una aplicación instalada en esta PC por nombre, por ejemplo notepad, chrome o calculadora.',schema({'name':string}),lambda name:open_target({'name':name})),
           FunctionTool('open_url','Abrí una URL HTTP o HTTPS en el navegador de esta PC.',schema({'url':string}),lambda url:open_target({'url':url}))]
    from data_tools import DATA_TOOLS,DATA_INSTRUCTIONS
    def data_query(name,**parameters):
        import httpx
        response=httpx.post('http://127.0.0.1:'+os.environ.get('JARVIS_PORT','8788')+'/api/data/execute',
                            json={'name':name,'arguments':parameters},timeout=35,trust_env=False)
        if not response.is_success:raise RuntimeError('La consulta de datos no está disponible.')
        return response.json()
    for definition in DATA_TOOLS:
        tools.append(FunctionTool(definition['name'],definition['description'],definition['parameters'],
                                  lambda _name=definition['name'],**params:data_query(_name,**params)))
    from integrations import INTEGRATION_TOOLS,INTEGRATION_INSTRUCTIONS
    def integration_query(name,**parameters):
        import httpx
        base='http://127.0.0.1:'+os.environ.get('JARVIS_PORT','8788')+'/api/integrations'
        if name=='list_integrations':
            response=httpx.get(base,params={'query':parameters.get('query','')},timeout=8,trust_env=False)
        else:
            response=httpx.post(base+'/'+parameters['integration_id']+'/call',json={'operation_id':parameters['operation_id'],'arguments':parameters.get('arguments',{})},timeout=30,trust_env=False)
        if not response.is_success:raise RuntimeError('La integración no confirmó la solicitud.')
        result=response.json()
        if result.get('status')=='needs_approval':emit('integration_approval',result=result)
        return result
    for definition in INTEGRATION_TOOLS:
        tools.append(FunctionTool(definition['name'],definition['description'],definition['parameters'],
                                  lambda _name=definition['name'],**params:integration_query(_name,**params)))
    def open_target(payload):
        import httpx
        response=httpx.post('http://127.0.0.1:'+os.environ.get('JARVIS_PORT','8788')+'/api/open',json=payload,timeout=15)
        response.raise_for_status();result=response.json()
        if not result.get('ok'):raise RuntimeError(result.get('error','No pude abrir ese destino.'))
        return result
    def before_tool(name,arguments):
        emit('tool',name=name,message={'file_write':'Creando un archivo','file_read':'Leyendo el proyecto','run_python':'Ejecutando un cálculo o programa','run_command':'Trabajando en el proyecto','web_search':'Buscando fuentes','remember':'Guardando memoria','system_report':'Consultando esta PC'}.get(name,'Usando '+name))
        return True
    history=Conversation(messages=[Message(role=Role(item['role']),content=item['content']) for item in job.get('history',[])])
    memory=json.dumps(agent_store.notes(),ensure_ascii=False)
    system=job['system_prompt']+f'\nCarpeta del proyecto: {workspace}. Memoria persistente: {memory}'
    system+='\nUsá create_spreadsheet para Excel y create_document para Word. Si piden abrir el archivo recién creado, usá open_artifact después de crearlo.'
    system+='\nSi piden crear una aplicación web y abrirla o ejecutarla, escribí un HTML autocontenido sin dependencias y después usá open_web_project con su nombre. Esa herramienta abre el archivo en Chrome o Edge y comprueba que haya una ventana visible. No sustituyas esa acción por abrir el navegador vacío ni por entregar un enlace.'
    system+=DATA_INSTRUCTIONS+'\nEn una misión, devolvé en el informe final los datos numéricos, fuentes y fechas para mostrarlos en pantalla.'
    system+='\n'+INTEGRATION_INSTRUCTIONS+' Si una integración devuelve needs_approval, informá que su ejecución sigue pendiente de confirmar en pantalla. No repitas la llamada ni afirmes haberla realizado. La decisión en pantalla ejecutará únicamente esa solicitud.'
    if provider=='claude':
        from openjarvis.learning.intelligence.orchestrator.prompt_registry import build_system_prompt
        system+='\n'+build_system_prompt(tools=tools)
        system+='\nLas herramientas de arriba las ejecuta el anfitrión OpenJarvis. Solicitá una por turno con TOOL e INPUT JSON; esperá Observation. No son herramientas nativas de esta consola Claude Code. Usá FINAL_ANSWER únicamente después de completar las solicitudes.'
    if provider=='local':system+='\nRespondé directamente en español. Contestá el pedido actual; el historial es contexto, no una orden pendiente. Nunca afirmes haber creado o verificado archivos sin usar las herramientas en esta misión. /no_think'
    agent=OrchestratorAgent(engine,job['model'],tools=tools,max_turns=job.get('max_turns',20),mode='structured' if provider=='claude' else 'function_calling',
                            max_tokens=8000,temperature=.3,system_prompt=system,
                            parallel_tools=False,before_tool_call=before_tool)
    result=agent.run(job['prompt'],context=AgentContext(conversation=history))
    for outcome in result.tool_results:
        emit('tool_result',name=outcome.tool_name,success=outcome.success,message=outcome.content[:1500])
    if result.metadata.get('max_turns_exceeded'):
        emit('error',message='La misión alcanzó el límite de pasos sin completar una respuesta. Los archivos creados siguen en el proyecto. Dividí el pedido en etapas.');return
    office_names={"create_spreadsheet","create_document","open_artifact"}
    performed=[outcome for outcome in result.tool_results if outcome.tool_name in office_names]
    content=result.content
    if performed:
        facts=[]
        if receipts:facts.append("Creé y verifiqué "+", ".join(r["path"] for r in receipts)+".")
        if opened:facts.append("Solicité abrir "+", ".join(opened)+".")
        for outcome in performed:
            if not outcome.success:facts.append(f"{outcome.tool_name}: {outcome.content[:240]}")
        if len(performed)!=len(result.tool_results):facts.append(result.content)
        if facts:content=" ".join(facts)
    emit('result',content=content,turns=result.turns,usage=result.metadata.get('usage',{}))

if __name__=='__main__':
    try:run(json.load(sys.stdin))
    except Exception as error:
        emit('error',message=str(error)[:2500]);sys.exit(1)
