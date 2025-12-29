from fastapi import FastAPI
from pydantic import BaseModel
import subprocess
import json

app = FastAPI()

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
        stdout, stderr = proc.communicate(input=input_json)

        if stderr:
            return {"exito": False, "mensaje": stderr}

        return json.loads(stdout)

    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
