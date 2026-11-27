"""Typed scientific operations: expressions are parsed by our AST visitor."""
import ast
import json
import math
import operator
import sys
import tempfile
from pathlib import Path

def limit_windows_memory(limit_bytes=1024**3):
    """Cap the worker's committed memory, including native scientific libraries."""
    import ctypes
    from ctypes import wintypes as w

    size = ctypes.c_size_t
    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
            ('flags', w.DWORD), ('min_working_set', size), ('max_working_set', size),
            ('active_processes', w.DWORD), ('affinity', size),
            ('priority_class', w.DWORD), ('scheduling_class', w.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ('basic', BasicLimits), ('io_counters', ctypes.c_uint64 * 6),
            ('process_memory', size), ('job_memory', size),
            ('peak_process_memory', size), ('peak_job_memory', size),
        ]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        limits.process_memory = limit_bytes
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        # An assigned job lives until all associated processes terminate.
        kernel.CloseHandle(job)

def main(job):
    import sympy as s
    functions={name:getattr(s,name) for name in ('sin','cos','tan','asin','acos','atan','exp','log','sqrt','Abs','Eq')}
    binary={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow}
    expression=job['expression'].replace('^','**')
    if len(expression)>2000:raise ValueError('La expresión es demasiado grande.')
    tree=ast.parse(expression,mode='eval')
    if len(list(ast.walk(tree)))>200:raise ValueError('La expresión tiene demasiados términos.')
    def parse(node):
        if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):
            if not math.isfinite(float(node.value)) or abs(node.value)>1e100:raise ValueError('Constante fuera del rango admitido.')
            return s.sympify(node.value)
        if isinstance(node,ast.Name) and node.id.isalnum() and not node.id.startswith('_'):
            return {'pi':s.pi,'E':s.E}.get(node.id,s.Symbol(node.id))
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return parse(node.operand)*(-1 if isinstance(node.op,ast.USub) else 1)
        if isinstance(node,ast.BinOp) and type(node.op) in binary:
            left,right=parse(node.left),parse(node.right)
            if isinstance(node.op,ast.Pow) and right.is_number:
                if abs(float(right))>1000:raise ValueError('Exponente demasiado grande.')
                if left.is_Integer and right.is_Integer and abs(int(left)).bit_length()*abs(int(right))>200000:raise ValueError('La potencia supera el presupuesto del cálculo.')
            return binary[type(node.op)](left,right)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in functions and not node.keywords:
            return functions[node.func.id](*(parse(argument) for argument in node.args))
        raise ValueError('Usá una expresión matemática: no se admiten atributos, archivos o código.')
    value=parse(tree.body)
    variable=job.get('variable','x')
    if not variable.isalnum() or variable.startswith('_'):raise ValueError('Variable no válida.')
    symbol=s.Symbol(variable)
    operation=job['operation']
    if operation=='solve':result=s.solve(value,symbol)
    elif operation=='differentiate':result=s.diff(value,symbol)
    elif operation=='integrate':result=s.integrate(value,symbol)
    elif operation=='simplify':result=s.simplify(value)
    elif operation=='plot':
        import numpy as np
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        lower=float(job.get('lower',-10));upper=float(job.get('upper',10))
        if not math.isfinite(lower+upper) or lower>=upper:raise ValueError('Rango no válido.')
        if value.free_symbols-{symbol}:raise ValueError('Para graficar, definí todas las constantes de la expresión.')
        xs=np.linspace(lower,upper,600);fn=s.lambdify(symbol,value,'numpy');ys=np.asarray(fn(xs))
        if ys.ndim==0:ys=np.full_like(xs,float(ys))
        folder=Path(job['workspace']).resolve();name=job.get('filename') or 'grafico.png'
        requested=Path(name);raw=requested if requested.is_absolute() else folder/requested
        if raw.is_symlink() or raw.is_junction():raise ValueError('El gráfico no puede reemplazar un enlace.')
        destination=raw.resolve()
        if not destination.is_relative_to(folder) or destination.suffix.lower()!='.png' or any(part.startswith('.') for part in destination.relative_to(folder).parts):raise ValueError('El gráfico debe ser un PNG dentro del proyecto.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.is_symlink() or destination.is_junction():raise ValueError('El destino del gráfico no puede ser un enlace.')
        with tempfile.NamedTemporaryFile(suffix='.png',prefix='grafico-',dir=folder,delete=False) as temporary:temp=Path(temporary.name)
        try:
            plt.figure(figsize=(9,5));plt.plot(xs,ys);plt.xlabel(variable);plt.ylabel(str(value));plt.grid(alpha=.25);plt.tight_layout();plt.savefig(temp,dpi=170);plt.close();temp.replace(destination)
        finally:temp.unlink(missing_ok=True)
        result={'file':destination.relative_to(folder).as_posix(),'expression':str(value),'range':[lower,upper]}
    else:raise ValueError('Operación no válida.')
    print(json.dumps({'result':str(result),'latex':s.latex(result) if operation!='plot' else ''},ensure_ascii=False))

if __name__=='__main__':
    try:
        if sys.platform == 'win32':
            limit_windows_memory()
        main(json.load(sys.stdin))
    except MemoryError:
        print(json.dumps({'error':'El cálculo superó el presupuesto de memoria.'}));sys.exit(1)
    except Exception as error:print(json.dumps({'error':str(error)},ensure_ascii=False));sys.exit(1)
