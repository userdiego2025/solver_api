from fastapi import FastAPI
from pydantic import BaseModel
import subprocess
import json

# Swagger, Redoc y OpenAPI habilitados explícitamente
app = FastAPI(
    title="Horario Solver API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# 🔹 Endpoint raíz (necesario para Railway health-check)
@app.get("/")
async def root():
    return {"status": "ok", "service": "solver_api"}


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
        # 🔹 Ejecutamos el solver con timeout para evitar bloqueos
        proc = subprocess.Popen(
            ["python3", "solver_horario.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        input_json = json.dumps(data.dict(), ensure_ascii=False)
        stdout, stderr = proc.communicate(input=input_json, timeout=60)

        # 🔹 Si el solver envía errores a stderr, los devolvemos
        if stderr and stderr.strip():
            return {
                "exito": False,
                "mensaje": "Error en solver",
                "detalle": stderr
            }

        # 🔹 Intentamos parsear JSON de salida
        try:
            return json.loads(stdout)
        except Exception:
            return {
                "exito": False,
                "mensaje": "Salida del solver no es JSON válido",
                "stdout": stdout
            }

    except subprocess.TimeoutExpired:
        return {
            "exito": False,
            "mensaje": "Tiempo de ejecución agotado (timeout)"
        }

    except Exception as e:
        return {
            "exito": False,
            "mensaje": str(e)
        }
