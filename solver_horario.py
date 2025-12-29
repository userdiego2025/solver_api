#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SOLVER DE HORARIOS - OR-Tools CP-SAT
Soporta FIN_SEMANA (1 día) y DIARIO (5 días)

Recibe JSON con:
- unidades: lista de cursos/bloques a asignar
- periodos_validos: índices de periodos disponibles
- grados: lista de grados
- bloques_equiv: dict {id_bloque: [indices de unidades]}
- modo_multidia: true/false (para PLAN DIARIO)
- dias: lista de días (solo si modo_multidia)
- periodos_por_dia: número de periodos por día (solo si modo_multidia)

Devuelve JSON con:
- exito: true/false
- asignaciones: {unidad_idx: periodo_idx} o {unidad_idx: {dia: X, periodo: Y}}
- mensaje: descripción del resultado
"""

import sys
import json
from ortools.sat.python import cp_model

def resolver_horario(datos):
    unidades = datos['unidades']
    periodos_validos = datos['periodos_validos']
    grados = datos['grados']
    bloques_equiv = datos.get('bloques_equiv', {})
    modo_multidia = datos.get('modo_multidia', False)
    dias = datos.get('dias', [])
    periodos_por_dia = datos.get('periodos_por_dia', len(periodos_validos))
    
    num_unidades = len(unidades)
    num_periodos = len(periodos_validos)
    
    if num_unidades == 0:
        return {'exito': True, 'asignaciones': {}, 'mensaje': 'No hay cursos para asignar'}
    
    # Crear conjunto de pares que son del mismo bloque
    mismo_bloque = set()
    for bloque_id, indices in bloques_equiv.items():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                mismo_bloque.add((min(indices[i], indices[j]), max(indices[i], indices[j])))
    
    model = cp_model.CpModel()
    
    if modo_multidia:
        # ============================================
        # MODO MULTIDÍA (PLAN DIARIO - 5 días)
        # ============================================
        num_dias = len(dias)
        num_slots = num_dias * periodos_por_dia
        
        # Variables: para cada unidad, en qué slot global va (día * periodos_por_dia + periodo)
        asignacion = {}
        for i in range(num_unidades):
            asignacion[i] = model.NewIntVar(0, num_slots - 1, f'unidad_{i}')
        
        # Funciones auxiliares para extraer día y periodo de un slot
        def get_dia(slot):
            return slot // periodos_por_dia
        def get_periodo(slot):
            return slot % periodos_por_dia
        
        # Restricción: Cursos del mismo bloque DEBEN ir en el mismo slot (mismo día y periodo)
        for bloque_id, indices in bloques_equiv.items():
            if len(indices) > 1:
                for i in range(1, len(indices)):
                    model.Add(asignacion[indices[0]] == asignacion[indices[i]])
        
        # Para restricciones de "mismo día", necesitamos variables adicionales
        dia_var = {}
        for i in range(num_unidades):
            dia_var[i] = model.NewIntVar(0, num_dias - 1, f'dia_{i}')
            # dia_var[i] = asignacion[i] // periodos_por_dia
            model.AddDivisionEquality(dia_var[i], asignacion[i], periodos_por_dia)
        
        periodo_var = {}
        for i in range(num_unidades):
            periodo_var[i] = model.NewIntVar(0, periodos_por_dia - 1, f'periodo_{i}')
            # periodo_var[i] = asignacion[i] % periodos_por_dia
            model.AddModuloEquality(periodo_var[i], asignacion[i], periodos_por_dia)
        
        # Restricción: Un docente no puede estar en dos lugares al mismo tiempo DEL MISMO DÍA
        # EXCEPTO si son del mismo bloque de equivalencia
        for i in range(num_unidades):
            for j in range(i + 1, num_unidades):
                par = (i, j)
                if par in mismo_bloque:
                    continue
                
                if unidades[i]['id_docente'] == unidades[j]['id_docente']:
                    # Si están en el mismo día, deben estar en diferente periodo
                    # Equivalente a: NOT (mismo_dia AND mismo_periodo)
                    # = NOT mismo_dia OR NOT mismo_periodo
                    # Usando variable auxiliar
                    mismo_dia = model.NewBoolVar(f'mismo_dia_{i}_{j}')
                    model.Add(dia_var[i] == dia_var[j]).OnlyEnforceIf(mismo_dia)
                    model.Add(dia_var[i] != dia_var[j]).OnlyEnforceIf(mismo_dia.Not())
                    
                    # Si mismo_dia es True, entonces periodo debe ser diferente
                    model.Add(periodo_var[i] != periodo_var[j]).OnlyEnforceIf(mismo_dia)
        
        # Restricción: Un grado no puede tener dos cursos al mismo tiempo (mismo día y periodo)
        for i in range(num_unidades):
            for j in range(i + 1, num_unidades):
                grados_i = set(unidades[i]['grados'])
                grados_j = set(unidades[j]['grados'])
                if grados_i & grados_j:
                    # Tienen grados en común, no pueden estar en el mismo slot
                    model.Add(asignacion[i] != asignacion[j])
        
        # Resolver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        solver.parameters.num_search_workers = 4
        
        status = solver.Solve(model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            resultado = {}
            for i in range(num_unidades):
                slot = solver.Value(asignacion[i])
                dia_idx = slot // periodos_por_dia
                periodo_idx = slot % periodos_por_dia
                resultado[i] = {
                    'dia': dias[dia_idx] if dia_idx < len(dias) else f'DIA_{dia_idx}',
                    'periodo': periodos_validos[periodo_idx] if periodo_idx < len(periodos_validos) else periodo_idx
                }
            
            return {
                'exito': True,
                'asignaciones': resultado,
                'mensaje': 'Solucion encontrada sin cruces',
                'status': 'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE',
                'modo': 'multidia'
            }
        else:
            mensaje = analizar_infactibilidad_multidia(unidades, periodos_por_dia, num_dias, grados, bloques_equiv, mismo_bloque)
            return {
                'exito': False,
                'asignaciones': {},
                'mensaje': mensaje,
                'status': 'INFEASIBLE',
                'modo': 'multidia'
            }
    
    else:
        # ============================================
        # MODO NORMAL (FIN_SEMANA - 1 día)
        # ============================================
        # Variables: para cada unidad, en qué periodo va
        asignacion = {}
        for i in range(num_unidades):
            asignacion[i] = model.NewIntVar(0, num_periodos - 1, f'unidad_{i}')
        
        # Restricción: Cursos del mismo bloque DEBEN ir en el mismo periodo
        for bloque_id, indices in bloques_equiv.items():
            if len(indices) > 1:
                for i in range(1, len(indices)):
                    model.Add(asignacion[indices[0]] == asignacion[indices[i]])
        
        # Restricción: Un docente no puede estar en dos lugares al mismo tiempo
        # EXCEPTO si son del mismo bloque de equivalencia
        for i in range(num_unidades):
            for j in range(i + 1, num_unidades):
                par = (i, j)
                if par in mismo_bloque:
                    continue
                
                if unidades[i]['id_docente'] == unidades[j]['id_docente']:
                    model.Add(asignacion[i] != asignacion[j])
        
        # Restricción: Un grado no puede tener dos cursos al mismo tiempo
        for i in range(num_unidades):
            for j in range(i + 1, num_unidades):
                grados_i = set(unidades[i]['grados'])
                grados_j = set(unidades[j]['grados'])
                if grados_i & grados_j:
                    model.Add(asignacion[i] != asignacion[j])
        
        # Resolver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0
        solver.parameters.num_search_workers = 4
        
        status = solver.Solve(model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            resultado = {}
            for i in range(num_unidades):
                periodo_idx_local = solver.Value(asignacion[i])
                periodo_real = periodos_validos[periodo_idx_local]
                resultado[i] = periodo_real
            
            return {
                'exito': True,
                'asignaciones': resultado,
                'mensaje': 'Solucion encontrada sin cruces',
                'status': 'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE',
                'modo': 'unidia'
            }
        else:
            mensaje = analizar_infactibilidad(unidades, periodos_validos, grados, bloques_equiv, mismo_bloque)
            return {
                'exito': False,
                'asignaciones': {},
                'mensaje': mensaje,
                'status': 'INFEASIBLE',
                'modo': 'unidia'
            }

def analizar_infactibilidad(unidades, periodos_validos, grados, bloques_equiv, mismo_bloque):
    """Analiza por qué no hay solución (modo un día)"""
    num_periodos = len(periodos_validos)
    
    cursos_por_docente = {}
    unidades_contadas = set()
    
    for bloque_id, indices in bloques_equiv.items():
        if indices:
            idx = indices[0]
            u = unidades[idx]
            doc = u['id_docente']
            nombre = u.get('docente_nombre', f'Docente {doc}')
            if doc not in cursos_por_docente:
                cursos_por_docente[doc] = {'nombre': nombre, 'count': 0}
            cursos_por_docente[doc]['count'] += 1
            for i in indices:
                unidades_contadas.add(i)
    
    for i, u in enumerate(unidades):
        if i in unidades_contadas:
            continue
        doc = u['id_docente']
        nombre = u.get('docente_nombre', f'Docente {doc}')
        if doc not in cursos_por_docente:
            cursos_por_docente[doc] = {'nombre': nombre, 'count': 0}
        cursos_por_docente[doc]['count'] += 1
    
    problemas = []
    for doc, info in cursos_por_docente.items():
        if info['count'] > num_periodos:
            exceso = info['count'] - num_periodos
            problemas.append(f"{info['nombre']}: {info['count']} cursos (excede por {exceso})")
    
    if problemas:
        return "No hay solucion sin cruces. Docentes con exceso:\n" + "\n".join(problemas)
    else:
        return "Restricciones demasiado estrictas para encontrar solucion."

def analizar_infactibilidad_multidia(unidades, periodos_por_dia, num_dias, grados, bloques_equiv, mismo_bloque):
    """Analiza por qué no hay solución (modo multidía)"""
    max_periodos = periodos_por_dia * num_dias
    
    cursos_por_docente = {}
    unidades_contadas = set()
    
    for bloque_id, indices in bloques_equiv.items():
        if indices:
            idx = indices[0]
            u = unidades[idx]
            doc = u['id_docente']
            nombre = u.get('docente_nombre', f'Docente {doc}')
            if doc not in cursos_por_docente:
                cursos_por_docente[doc] = {'nombre': nombre, 'count': 0}
            cursos_por_docente[doc]['count'] += 1
            for i in indices:
                unidades_contadas.add(i)
    
    for i, u in enumerate(unidades):
        if i in unidades_contadas:
            continue
        doc = u['id_docente']
        nombre = u.get('docente_nombre', f'Docente {doc}')
        if doc not in cursos_por_docente:
            cursos_por_docente[doc] = {'nombre': nombre, 'count': 0}
        cursos_por_docente[doc]['count'] += 1
    
    problemas = []
    for doc, info in cursos_por_docente.items():
        if info['count'] > max_periodos:
            exceso = info['count'] - max_periodos
            problemas.append(f"{info['nombre']}: {info['count']} cursos (excede {max_periodos} slots por {exceso})")
    
    if problemas:
        return f"No hay solucion sin cruces ({num_dias} dias x {periodos_por_dia} periodos = {max_periodos} slots). Docentes:\n" + "\n".join(problemas)
    else:
        return "Restricciones demasiado estrictas para encontrar solucion."

def main():
    try:
        input_data = sys.stdin.read()
        datos = json.loads(input_data)
        resultado = resolver_horario(datos)
        print(json.dumps(resultado, ensure_ascii=False))
    except Exception as e:
        error = {
            'exito': False,
            'asignaciones': {},
            'mensaje': f'Error en solver: {str(e)}',
            'status': 'ERROR'
        }
        print(json.dumps(error, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__':
    main()
