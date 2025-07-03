from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import math
from ortools.sat.python import cp_model

# --- MODELOS DE DATOS ---
class Piece(BaseModel):
    id: str; width: float; height: float; quantity: int = 1
class Sheet(BaseModel):
    width: float; height: float
class OptimizationRequest(BaseModel):
    material_type: Literal["sheet", "roll"]; sheet: Sheet; pieces: List[Piece]; kerf: float = 0; respect_grain: bool = False
    cutting_speed_mms: float; sheet_thickness_mm: float = 0; cut_depth_per_pass_mm: float = 0

# --- CONFIGURACIÓN DE FASTAPI Y CORS ---
app = FastAPI(
    title="API de Optimización de Corte con OR-Tools (Estable)",
    description="Solver de máxima densidad con lógica simplificada y robusta.",
    version="13.1.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # 1. Desempaquetar piezas y añadir kerf
    unpacked_pieces = []
    original_pieces_map = {}
    rotation_allowed = not request.respect_grain

    for piece in request.pieces:
        for i in range(piece.quantity):
            new_id = f"{piece.id}-{i+1}" if piece.quantity > 1 else piece.id
            
            w = int(piece.width + request.kerf)
            h = int(piece.height + request.kerf)

            # Heurística de pre-rotación: si se permite, orientar la pieza para que sea más alta que ancha
            # Esto ayuda a los algoritmos de empaquetado a ser más eficientes.
            is_rotated = False
            if rotation_allowed and w > h:
                w, h = h, w
                is_rotated = True

            unpacked_pieces.append({"id": new_id, "width": w, "height": h, "rotated_pre": is_rotated})
            original_pieces_map[new_id] = piece

    sheet_width = int(request.sheet.width)
    # Para rollos, la altura es "infinita"; para láminas, es fija.
    sheet_height_limit = sum(p['height'] for p in unpacked_pieces) + 1 if request.material_type == 'roll' else int(request.sheet.height)
    
    model = cp_model.CpModel()

    # --- VARIABLES ---
    # Para cada pieza, variables para sus coordenadas de inicio (x, y)
    x_vars = {p['id']: model.NewIntVar(0, sheet_width - p['width'], f"x_{p['id']}") for p in unpacked_pieces}
    y_vars = {p['id']: model.NewIntVar(0, sheet_height_limit - p['height'], f"y_{p['id']}") for p in unpacked_pieces}
    
    # Variables de intervalo para las dimensiones en x e y
    x_intervals = [model.NewIntervalVar(x_vars[p['id']], p['width'], x_vars[p['id']] + p['width'], f"xi_{p['id']}") for p in unpacked_pieces]
    y_intervals = [model.NewIntervalVar(y_vars[p['id']], p['height'], y_vars[p['id']] + p['height'], f"yi_{p['id']}") for p in unpacked_pieces]

    # --- RESTRICCIONES ---
    # 1. No solapamiento: Esta es la restricción clave.
    model.AddNoOverlap2D(x_intervals, y_intervals)

    # 2. Límites del contenedor (ya implícitos en la definición de las variables, pero esto es más seguro)
    for p in unpacked_pieces:
        model.Add(x_vars[p['id']] + p['width'] <= sheet_width)
        model.Add(y_vars[p['id']] + p['height'] <= sheet_height_limit)

    # --- OBJETIVO ---
    # Minimizar el largo del rollo o la altura de la lámina
    max_height_var = model.NewIntVar(0, sheet_height_limit, 'max_height')
    for p in unpacked_pieces:
        model.Add(max_height_var >= y_vars[p['id']] + p['height'])
    model.Minimize(max_height_var)
    
    # --- RESOLVER EL PROBLEMA ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0  # Límite de tiempo
    solver.parameters.log_search_progress = True # Ayuda a ver qué está haciendo el solver
    status = solver.Solve(model)

    # --- PROCESAR RESULTADOS ---
    placed_pieces = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for i, p_data in enumerate(unpacked_pieces):
            p_id = p_data['id']
            original_piece = original_pieces_map[p_id]
            
            # Comprobamos si la pieza está realmente dentro de los límites de la lámina (para casos de no solución)
            y_val = solver.Value(y_vars[p_id])
            if request.material_type == 'sheet' and y_val >= sheet_height_limit:
                continue

            placed_pieces.append({
                "id": p_id,
                "x": solver.Value(x_vars[p_id]),
                "y": y_val,
                "width": original_piece.width if not p_data['rotated_pre'] else original_piece.height,
                "height": original_piece.height if not p_data['rotated_pre'] else original_piece.width,
                "rotated": p_data['rotated_pre']
            })

    all_placed_ids = {p['id'] for p in placed_pieces}
    impossible_ids = [p_id for p_id in original_pieces_map if p_id not in all_placed_ids]
    
    # --- El resto del código de cálculo de métricas es idéntico a tu versión y correcto ---
    total_placed_piece_area = sum(p['width'] * p['height'] for p in placed_pieces)
    total_cut_length_mm = sum(2 * (p['width'] + p['height']) for p in placed_pieces)

    if request.material_type == 'roll':
        consumed_length = solver.ObjectiveValue() if placed_pieces else 0
        total_material_area = request.sheet.width * consumed_length
        final_sheet_height = consumed_length if consumed_length > 0 else 1
    else:
        total_material_area = request.sheet.width * request.sheet.height
        final_sheet_height = request.sheet.height
        
    waste_percentage = ((total_material_area - total_placed_piece_area) / total_material_area) * 100 if total_material_area > 0 else 0
    total_material_area_sqm = total_material_area / 1_000_000
    
    num_passes = 1
    if request.material_type == 'sheet' and request.sheet_thickness_mm > 0 and request.cut_depth_per_pass_mm > 0:
        num_passes = math.ceil(request.sheet_thickness_mm / request.cut_depth_per_pass_mm)
    
    total_path_distance = total_cut_length_mm * num_passes
    estimated_time_seconds = total_path_distance / request.cutting_speed_mms if request.cutting_speed_mms > 0 else 0
    
    return {
        "sheets": [{"sheet_index": 1, "sheet_dimensions": {"width": request.sheet.width, "height": final_sheet_height}, "placed_pieces": placed_pieces, "metrics": {"piece_count": len(placed_pieces)}}] if placed_pieces else [],
        "impossible_to_place_ids": impossible_ids, "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type, "total_sheets_used": 1 if placed_pieces else 0,
            "total_pieces": len(original_pieces_map), "total_placed_pieces": len(placed_pieces),
            "waste_percentage": round(waste_percentage, 2),
            "total_material_area_sqm": round(total_material_area_sqm, 2),
            "estimated_time_seconds": round(estimated_time_seconds)
        }
    }