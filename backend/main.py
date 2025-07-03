from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import math
from ortools.sat.python import cp_model

# --- MODELOS DE DATOS ---
class Piece(BaseModel):
    id: str
    width: float
    height: float
    quantity: int = 1

class Sheet(BaseModel):
    width: float
    height: float

class OptimizationRequest(BaseModel):
    material_type: Literal["sheet", "roll"]
    sheet: Sheet
    pieces: List[Piece]
    kerf: float = 0
    respect_grain: bool = False
    cutting_speed_mms: float
    sheet_thickness_mm: float = 0
    cut_depth_per_pass_mm: float = 0

# --- CONFIGURACIÓN DE FASTAPI Y CORS ---
app = FastAPI(
    title="API de Optimización de Corte con Google OR-Tools v2",
    description="Solver mejorado con rotación de piezas y empaquetado múltiple.",
    version="12.1.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # 1. Desempaquetar piezas
    unpacked_pieces = []
    original_pieces_map = {}
    for piece in request.pieces:
        for i in range(piece.quantity):
            new_id = f"{piece.id}-{i+1}" if piece.quantity > 1 else piece.id
            unpacked_pieces.append({
                "id": new_id,
                "width": int(piece.width + request.kerf),
                "height": int(piece.height + request.kerf)
            })
            original_pieces_map[new_id] = piece

    sheet_width = int(request.sheet.width)
    sheet_height_limit = 999999 if request.material_type == 'roll' else int(request.sheet.height)
    rotation_allowed = not request.respect_grain
    
    model = cp_model.CpModel()

    # --- VARIABLES ---
    # Para cada pieza, variables para coordenadas y si está rotada
    x_vars = {p['id']: model.NewIntVar(0, sheet_width, f"x_{p['id']}") for p in unpacked_pieces}
    y_vars = {p['id']: model.NewIntVar(0, sheet_height_limit, f"y_{p['id']}") for p in unpacked_pieces}
    rotated_vars = {p['id']: model.NewBoolVar(f"r_{p['id']}") for p in unpacked_pieces} if rotation_allowed else {}

    # Variables de intervalo para las dimensiones en x e y
    x_intervals = {}
    y_intervals = {}

    for p in unpacked_pieces:
        width, height = p['width'], p['height']
        # Dimensiones efectivas basadas en la rotación
        if rotation_allowed and width != height:
            is_rotated = rotated_vars[p['id']]
            # Si se rota, las dimensiones se intercambian
            w = model.NewIntVar(0, sheet_width, f"w_{p['id']}")
            h = model.NewIntVar(0, sheet_height_limit, f"h_{p['id']}")
            model.Add(w == width).OnlyEnforceIf(is_rotated.Not())
            model.Add(h == height).OnlyEnforceIf(is_rotated.Not())
            model.Add(w == height).OnlyEnforceIf(is_rotated)
            model.Add(h == width).OnlyEnforceIf(is_rotated)
        else:
            w, h = width, height

        x_intervals[p['id']] = model.NewIntervalVar(x_vars[p['id']], w, x_vars[p['id']] + w, f"xi_{p['id']}")
        y_intervals[p['id']] = model.NewIntervalVar(y_vars[p['id']], h, y_vars[p['id']] + h, f"yi_{p['id']}")

    # --- RESTRICCIONES ---
    # 1. No solapamiento: Añadir una restricción de no solapamiento en 2D
    model.AddNoOverlap2D(list(x_intervals.values()), list(y_intervals.values()))

    # 2. Límites del contenedor
    for p in unpacked_pieces:
        model.Add(x_vars[p['id']] + x_intervals[p['id']].SizeExpr() <= sheet_width)
        if request.material_type == 'sheet':
            model.Add(y_vars[p['id']] + y_intervals[p['id']].SizeExpr() <= sheet_height_limit)

    # --- OBJETIVO ---
    # Minimizar el largo del rollo o la altura de la lámina
    max_height_var = model.NewIntVar(0, sheet_height_limit, 'max_height')
    for p in unpacked_pieces:
        model.Add(max_height_var >= y_vars[p['id']] + y_intervals[p['id']].SizeExpr())
    model.Minimize(max_height_var)
    
    # --- RESOLVER EL PROBLEMA ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0  # Límite de tiempo
    status = solver.Solve(model)

    # --- PROCESAR RESULTADOS ---
    placed_pieces = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for p_data in unpacked_pieces:
            p_id = p_data['id']
            is_rotated = solver.Value(rotated_vars[p_id]) if p_id in rotated_vars else False
            original_piece = original_pieces_map[p_id]
            
            placed_pieces.append({
                "id": p_id,
                "x": solver.Value(x_vars[p_id]),
                "y": solver.Value(y_vars[p_id]),
                "width": original_piece.width,
                "height": original_piece.height,
                "rotated": is_rotated
            })

    all_placed_ids = {p['id'] for p in placed_pieces}
    impossible_ids = [p_id for p_id in original_pieces_map if p_id not in all_placed_ids]
    
    total_placed_piece_area = sum(p['width'] * p['height'] for p in placed_pieces)
    total_cut_length_mm = sum(2 * (p['width'] + p['height']) for p in placed_pieces)

    if request.material_type == 'roll':
        consumed_length = solver.ObjectiveValue()
        total_material_area = request.sheet.width * consumed_length
        final_sheet_height = consumed_length
    else:
        # Para una sola lámina, el área es la de la lámina
        total_material_area = request.sheet.width * request.sheet.height
        final_sheet_height = request.sheet.height
        
    waste_percentage = ((total_material_area - total_placed_piece_area) / total_material_area) * 100 if total_material_area > 0 else 0
    total_material_area_sqm = total_material_area / 1_000_000
    
    num_passes = 1
    if request.material_type == 'sheet' and request.sheet_thickness_mm > 0 and request.cut_depth_per_pass_mm > 0:
        num_passes = math.ceil(request.sheet_thickness_mm / request.cut_depth_per_pass_mm)
    
    total_path_distance = total_cut_length_mm * num_passes
    estimated_time_seconds = total_path_distance / request.cutting_speed_mms if request.cutting_speed_mms > 0 else 0
    
    # NOTA: Este solver actual solo maneja 1 lámina. La lógica de múltiples láminas con OR-Tools es mucho más compleja.
    # Devolvemos un array con una sola lámina como resultado.
    return {
        "sheets": [{
            "sheet_index": 1,
            "sheet_dimensions": {"width": request.sheet.width, "height": final_sheet_height},
            "placed_pieces": placed_pieces,
            "metrics": {"piece_count": len(placed_pieces)}
        }] if placed_pieces else [],
        "impossible_to_place_ids": impossible_ids,
        "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type,
            "total_sheets_used": 1 if placed_pieces else 0,
            "total_pieces": len(original_pieces_map),
            "total_placed_pieces": len(placed_pieces),
            "waste_percentage": round(waste_percentage, 2),
            "total_material_area_sqm": round(total_material_area_sqm, 2),
            "estimated_time_seconds": round(estimated_time_seconds)
        }
    }