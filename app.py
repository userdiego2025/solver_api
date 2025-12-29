from fastapi import FastAPI
from pydantic import BaseModel
import subprocess
import json

app = FastAPI(
    title="Horario Solver API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/ping")
async def ping():
    return "pong"

class SolverInput(BaseModel):
    unidades: list
    periodos_validos: list
    grados: list
    bloques_equiv: dict = {}
    modo_multidia: bool = False
    dias: list = []
    periodos_por_dia: int = 0

@app.post("/solve")
async def solve(data: SolverInput):
    try:
        proc = subprocess.Popen(
            ["python3", "solver_horario.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        input_json = json.dumps(data.dict(), ensure_ascii=False)

        stdout, stderr = proc.communicate(input=input_json, timeout=60)

        if stderr and stderr.strip():
            return {"exito": False, "mensaje": stderr}

        return json.loads(stdout)

    except subprocess.TimeoutExpired:
        proc.kill()
        return {"exito": False, "mensaje": "Tiempo de ejecución excedido (timeout)"}

    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
