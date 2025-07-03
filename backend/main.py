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
    title="API de Optimización de Corte con OR-Tools (Final)",
    description="Solver de máxima densidad con lógica iterativa para velocidad y estabilidad.",
    version="14.1.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- NUEVA FUNCIÓN HELPER PARA OPTIMIZAR UN SOLO BIN ---
def optimize_single_bin(pieces_to_pack, sheet_width, sheet_height, rotation_allowed, kerf):
    model = cp_model.CpModel()
    
    # Crear variables para cada pieza
    x_vars = {p['id']: model.NewIntVar(0, sheet_width, f"x_{p['id']}") for p in pieces_to_pack}
    y_vars = {p['id']: model.NewIntVar(0, sheet_height, f"y_{p['id']}") for p in pieces_to_pack}
    
    x_intervals, y_intervals = {}, {}
    rotated_vars = {}

    for p in pieces_to_pack:
        p_id, width, height = p['id'], p['width'], p['height']
        
        # Variables de rotación (si se permite)
        if rotation_allowed and width != height:
            is_rotated = model.NewBoolVar(f"r_{p_id}")
            rotated_vars[p_id] = is_rotated
            
            # Intervalos opcionales para ambas orientaciones
            x_intervals[p_id] = model.NewOptionalIntervalVar(x_vars[p_id], width, x_vars[p_id] + width, is_rotated.Not(), f"xi_{p_id}")
            y_intervals[p_id] = model.NewOptionalIntervalVar(y_vars[p_id], height, y_vars[p_id] + height, is_rotated.Not(), f"yi_{p_id}")
            x_intervals[f"{p_id}_rot"] = model.NewOptionalIntervalVar(x_vars[p_id], height, x_vars[p_id] + height, is_rotated, f"xi_rot_{p_id}")
            y_intervals[f"{p_id}_rot"] = model.NewOptionalIntervalVar(y_vars[p_id], width, y_vars[p_id] + width, is_rotated, f"yi_rot_{p_id}")
        else:
            x_intervals[p_id] = model.NewIntervalVar(x_vars[p_id], width, x_vars[p_id] + width, f"xi_{p_id}")
            y_intervals[p_id] = model.NewIntervalVar(y_vars[p_id], height, y_vars[p_id] + height, f"yi_{p_id}")

    # Restricción de no solapamiento
    model.AddNoOverlap2D(list(x_intervals.values()), list(y_intervals.values()))

    # Restricción de límites
    for interval in x_intervals.values(): model.Add(interval.EndExpr() <= sheet_width)
    for interval in y_intervals.values(): model.Add(interval.EndExpr() <= sheet_height)
    
    # Objetivo: Maximizar el número de piezas colocadas en este bin
    placed_literals = [i.IsPresent() for i in x_intervals.values()]
    model.Maximize(sum(placed_literals))

    # Resolver el problema para este bin
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0
    status = solver.Solve(model)

    placed_in_this_bin = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for p_data in pieces_to_pack:
            p_id = p_data['id']
            # Comprobar si la pieza fue realmente colocada
            if solver.BooleanValue(x_intervals[p_id].IsPresent()):
                is_rotated = solver.Value(rotated_vars[p_id]) if p_id in rotated_vars else False
                width_no_kerf = p_data['width'] - kerf if not is_rotated else p_data['height'] - kerf
                height_no_kerf = p_data['height'] - kerf if not is_rotated else p_data['width'] - kerf

                placed_in_this_bin.append({
                    "id": p_id, "x": solver.Value(x_vars[p_id]), "y": solver.Value(y_vars[p_id]),
                    "width": width_no_kerf, "height": height_no_kerf, "rotated": is_rotated
                })
    return placed_in_this_bin

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    unpacked_pieces = []
    for piece in request.pieces:
        for i in range(piece.quantity):
            unpacked_pieces.append({"id": f"{piece.id}-{i+1}" if piece.quantity > 1 else piece.id, "width": int(piece.width), "height": int(piece.height)})

    sheet_width = int(request.sheet.width)
    sheet_height = 9999999 if request.material_type == 'roll' else int(request.sheet.height)
    rotation_allowed = not request.respect_grain
    kerf = int(request.kerf)
    
    # --- LÓGICA ITERATIVA CON OR-TOOLS ---
    pieces_to_pack = [{"id": p['id'], "width": p['width'] + kerf, "height": p['height'] + kerf} for p in unpacked_pieces]
    packed_sheets = []
    sheet_index = 0

    while pieces_to_pack:
        sheet_index += 1
        print(f"--- Optimizando Lámina #{sheet_index} con {len(pieces_to_pack)} piezas restantes ---")
        
        placed_this_run = optimize_single_bin(pieces_to_pack, sheet_width, sheet_height, rotation_allowed, kerf)
        
        if not placed_this_run:
            print("No se pudieron colocar más piezas. Terminando.")
            break
            
        packed_sheets.append({
            "sheet_index": sheet_index,
            "sheet_dimensions": {"width": sheet_width, "height": sheet_height},
            "placed_pieces": placed_this_run,
            "metrics": {"piece_count": len(placed_this_run)}
        })
        
        placed_ids = {p['id'] for p in placed_this_run}
        pieces_to_pack = [p for p in pieces_to_pack if p['id'] not in placed_ids]

    # --- PROCESAR RESULTADOS FINALES ---
    all_placed_ids = {p['id'] for s in packed_sheets for p in s['placed_pieces']}
    impossible_ids = [p['id'] for p in unpacked_pieces if p['id'] not in all_placed_ids]
    
    total_placed_piece_area = sum(p['width'] * p['height'] for s in packed_sheets for p in s['placed_pieces'])
    total_cut_length_mm = sum(2 * (p['width'] + p['height']) for s in packed_sheets for p in s['placed_pieces'])
    
    if request.material_type == 'roll' and packed_sheets:
        max_y = max((p['y'] + p['height'] for p in packed_sheets[0]['placed_pieces']), default=0)
        consumed_length = max_y
        packed_sheets[0]['sheet_dimensions']['height'] = consumed_length if consumed_length > 0 else 1
        total_material_area = request.sheet.width * consumed_length
    else:
        total_material_area = len(packed_sheets) * request.sheet.width * request.sheet.height
        
    waste_percentage = ((total_material_area - total_placed_piece_area) / total_material_area) * 100 if total_material_area > 0 else 0
    total_material_area_sqm = total_material_area / 1_000_000
    
    num_passes = math.ceil(request.sheet_thickness_mm / request.cut_depth_per_pass_mm) if request.material_type == 'sheet' and request.sheet_thickness_mm > 0 and request.cut_depth_per_pass_mm > 0 else 1
    total_path_distance = total_cut_length_mm * num_passes
    estimated_time_seconds = total_path_distance / request.cutting_speed_mms if request.cutting_speed_mms > 0 else 0
    
    return {
        "sheets": packed_sheets, "impossible_to_place_ids": impossible_ids, "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type, "total_sheets_used": len(packed_sheets),
            "total_pieces": len(unpacked_pieces), "total_placed_pieces": len(all_placed_ids),
            "waste_percentage": round(waste_percentage, 2),
            "total_material_area_sqm": round(total_material_area_sqm, 2),
            "estimated_time_seconds": round(estimated_time_seconds)
        }
    }