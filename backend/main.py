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
    version="14.2.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- NUEVA FUNCIÓN HELPER PARA OPTIMIZAR UN SOLO BIN ---
def optimize_single_bin(pieces_to_pack, sheet_width, sheet_height):
    model = cp_model.CpModel()
    
    # Crear variables para cada pieza
    x_vars = {p['id']: model.NewIntVar(0, sheet_width - p['width'], f"x_{p['id']}") for p in pieces_to_pack}
    y_vars = {p['id']: model.NewIntVar(0, sheet_height - p['height'], f"y_{p['id']}") for p in pieces_to_pack}
    
    x_intervals = [model.NewIntervalVar(x_vars[p['id']], p['width'], x_vars[p['id']] + p['width'], f"xi_{p['id']}") for p in pieces_to_pack]
    y_intervals = [model.NewIntervalVar(y_vars[p['id']], p['height'], y_vars[p['id']] + p['height'], f"yi_{p['id']}") for p in pieces_to_pack]

    # Variable booleana para cada pieza, que será verdadera si se coloca
    placed_literals = {p['id']: model.NewBoolVar(f"placed_{p['id']}") for p in pieces_to_pack}

    # Modificamos AddNoOverlap2D para usar intervalos opcionales
    optional_x_intervals = [model.NewOptionalIntervalVar(x.StartExpr(), x.SizeExpr(), x.EndExpr(), placed_literals[p['id']], f"oxi_{p['id']}") for p, x in zip(pieces_to_pack, x_intervals)]
    optional_y_intervals = [model.NewOptionalIntervalVar(y.StartExpr(), y.SizeExpr(), y.EndExpr(), placed_literals[p['id']], f"oyi_{p['id']}") for p, y in zip(pieces_to_pack, y_intervals)]
    model.AddNoOverlap2D(optional_x_intervals, optional_y_intervals)

    # Objetivo: Maximizar el área total de las piezas colocadas
    total_area_placed = model.NewIntVar(0, sheet_width * sheet_height, 'total_area')
    model.Add(total_area_placed == sum(p['width'] * p['height'] * placed_literals[p['id']] for p in pieces_to_pack))
    model.Maximize(total_area_placed)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    status = solver.Solve(model)

    placed_in_this_bin = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for p_data in pieces_to_pack:
            if solver.BooleanValue(placed_literals[p_data['id']]):
                placed_in_this_bin.append({
                    "id": p_data['id'],
                    "x": solver.Value(x_vars[p_data['id']]), "y": solver.Value(y_vars[p_data['id']]),
                    "width": p_data['width'], "height": p_data['height'], "rotated": p_data['rotated']
                })
    return placed_in_this_bin

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # 1. Desempaquetar piezas
    unpacked_pieces_input = []
    for piece in request.pieces:
        for i in range(piece.quantity):
            unpacked_pieces_input.append({"id": f"{piece.id}-{i+1}" if piece.quantity > 1 else piece.id, "width": int(piece.width), "height": int(piece.height)})

    sheet_width = int(request.sheet.width)
    sheet_height = 9999999 if request.material_type == 'roll' else int(request.sheet.height)
    kerf = int(request.kerf)
    rotation_allowed = not request.respect_grain
    
    # 2. Preparar la lista de piezas, aplicando rotación y kerf si es necesario
    pieces_to_pack = []
    impossible_ids = []

    for p in unpacked_pieces_input:
        w, h = p['width'] + kerf, p['height'] + kerf
        
        can_fit_normal = w <= sheet_width and h <= sheet_height
        can_fit_rotated = h <= sheet_width and w <= sheet_height
        
        if not can_fit_normal and (not rotation_allowed or not can_fit_rotated):
            impossible_ids.append(p['id'])
            continue

        is_rotated = False
        # Si se permite la rotación y la pieza solo cabe rotada, forzar rotación
        if rotation_allowed and not can_fit_normal and can_fit_rotated:
            w, h = h, w
            is_rotated = True
            
        pieces_to_pack.append({"id": p['id'], "width": w, "height": h, "rotated": is_rotated, "original_width": p['width'], "original_height": p['height']})

    # 3. Lógica iterativa con OR-Tools
    packed_sheets = []
    sheet_index = 0
    final_impossible_ids = list(impossible_ids) # Empezar con las que ya sabemos que no caben

    while pieces_to_pack:
        sheet_index += 1
        print(f"--- Optimizando Lámina #{sheet_index} con {len(pieces_to_pack)} piezas restantes ---")
        
        placed_this_run_raw = optimize_single_bin(pieces_to_pack, sheet_width, sheet_height)
        
        if not placed_this_run_raw:
            print("No se pudieron colocar más piezas. Añadiendo restantes a imposibles.")
            final_impossible_ids.extend([p['id'] for p in pieces_to_pack])
            break
        
        # Revertir el kerf para la respuesta y obtener dimensiones originales
        placed_this_run = []
        for p in placed_this_run_raw:
            p_orig = next((item for item in pieces_to_pack if item["id"] == p["id"]), None)
            placed_this_run.append({
                "id": p['id'], "x": p['x'], "y": p['y'],
                "width": p_orig['original_width'], 
                "height": p_orig['original_height'],
                "rotated": p_orig['rotated']
            })

        packed_sheets.append({
            "sheet_index": sheet_index,
            "sheet_dimensions": {"width": sheet_width, "height": sheet_height},
            "placed_pieces": placed_this_run, "metrics": {"piece_count": len(placed_this_run)}
        })
        
        placed_ids = {p['id'] for p in placed_this_run}
        pieces_to_pack = [p for p in pieces_to_pack if p['id'] not in placed_ids]
    
    # --- PROCESAR RESULTADOS FINALES ---
    all_placed_ids = {p['id'] for s in packed_sheets for p in s['placed_pieces']}
    
    total_placed_piece_area = sum(p['width'] * p['height'] for s in packed_sheets for p in s['placed_pieces'])
    total_cut_length_mm = sum(2 * (p['width'] + p['height']) for s in packed_sheets for p in s['placed_pieces'])
    
    if request.material_type == 'roll' and packed_sheets:
        max_y = max((p['y'] + p['height'] + kerf for p in packed_sheets[0]['placed_pieces']), default=0)
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
        "sheets": packed_sheets,
        "impossible_to_place_ids": final_impossible_ids,
        "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type,
            "total_sheets_used": len(packed_sheets),
            "total_pieces": len(unpacked_pieces_input),
            "total_placed_pieces": len(all_placed_ids),
            "waste_percentage": round(waste_percentage, 2),
            "total_material_area_sqm": round(total_material_area_sqm, 2),
            "estimated_time_seconds": round(estimated_time_seconds)
        }
    }