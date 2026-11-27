"""Execute an explicitly approved command, including tree cleanup on timeout."""
import subprocess

def execute(command,workspace,environment,timeout):
    process=subprocess.Popen(command,cwd=workspace,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        out,err=process.communicate(timeout=timeout)
        return {'exit_code':process.returncode,'stdout':out[-22000:],'stderr':err[-6000:]}
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill','/T','/F','/PID',str(process.pid)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        out,err=process.communicate(timeout=10)
        return {'exit_code':-1,'stdout':out[-22000:],'stderr':err[-5000:]+'\nSe agotó el tiempo de ejecución; se detuvo el árbol de procesos.'}
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)
