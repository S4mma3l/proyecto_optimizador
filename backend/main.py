from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import math
from ortools.sat.python import cp_model

# --- MODELOS DE DATOS (Tu versión, sin cambios) ---
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

# --- CONFIGURACIÓN DE FASTAPI Y CORS (sin cambios) ---
app = FastAPI(
    title="API de Optimización de Corte con Google OR-Tools v12.2",
    description="Solver mejorado con corrección de TypeError para rotación avanzada.",
    version="12.2.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # 1. Desempaquetar piezas (tu lógica)
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

    # 2. Configurar dimensiones (tu lógica)
    sheet_width = int(request.sheet.width)
    sheet_height_limit = sum(p['height'] for p in unpacked_pieces) if request.material_type == 'roll' else int(request.sheet.height)
    rotation_allowed = not request.respect_grain
    
    model = cp_model.CpModel()

    # --- VARIABLES (tu lógica) ---
    x_vars = {p['id']: model.NewIntVar(0, sheet_width, f"x_{p['id']}") for p in unpacked_pieces}
    y_vars = {p['id']: model.NewIntVar(0, sheet_height_limit, f"y_{p['id']}") for p in unpacked_pieces}
    rotated_vars = {p['id']: model.NewBoolVar(f"r_{p['id']}") for p in unpacked_pieces if rotation_allowed and p['width'] != p['height']}
    
    # --- ¡AQUÍ ESTÁ LA CORRECCIÓN! ---
    x_intervals, y_intervals = {}, {}
    for p in unpacked_pieces:
        width, height = p['width'], p['height']
        
        # Variables para las dimensiones efectivas
        effective_w = model.NewIntVar(0, sheet_width, f"w_{p['id']}")
        effective_h = model.NewIntVar(0, sheet_height_limit, f"h_{p['id']}")

        # Variables para las coordenadas finales
        end_x = model.NewIntVar(0, sheet_width, f"end_x_{p['id']}")
        end_y = model.NewIntVar(0, sheet_height_limit, f"end_y_{p['id']}")

        if p['id'] in rotated_vars:
            is_rotated = rotated_vars[p['id']]
            # Si se rota, las dimensiones se intercambian
            model.Add(effective_w == height).OnlyEnforceIf(is_rotated)
            model.Add(effective_h == width).OnlyEnforceIf(is_rotated)
            # Si no se rota, mantienen sus dimensiones originales
            model.Add(effective_w == width).OnlyEnforceIf(is_rotated.Not())
            model.Add(effective_h == height).OnlyEnforceIf(is_rotated.Not())
        else:
            # Si no se permite rotación, las dimensiones son fijas
            model.Add(effective_w == width)
            model.Add(effective_h == height)
        
        # Enlazar las coordenadas de fin con las de inicio y el tamaño
        model.Add(end_x == x_vars[p['id']] + effective_w)
        model.Add(end_y == y_vars[p['id']] + effective_h)
        
        # Ahora sí, crear las variables de intervalo con expresiones válidas
        x_intervals[p['id']] = model.NewIntervalVar(x_vars[p['id']], effective_w, end_x, f"xi_{p['id']}")
        y_intervals[p['id']] = model.NewIntervalVar(y_vars[p['id']], effective_h, end_y, f"yi_{p['id']}")

    # --- RESTRICCIONES (tu lógica, ahora funciona) ---
    model.AddNoOverlap2D(list(x_intervals.values()), list(y_intervals.values()))
    
    for p in unpacked_pieces:
        model.Add(x_vars[p['id']] + x_intervals[p['id']].SizeExpr() <= sheet_width)
        if request.material_type == 'sheet':
            model.Add(y_vars[p['id']] + y_intervals[p['id']].SizeExpr() <= sheet_height_limit)

    # --- OBJETIVO (tu lógica) ---
    max_height_var = model.NewIntVar(0, sheet_height_limit, 'max_height')
    for p in unpacked_pieces:
        model.Add(max_height_var >= y_vars[p['id']] + y_intervals[p['id']].SizeExpr())
    model.Minimize(max_height_var)
    
    # --- RESOLVER EL PROBLEMA (tu lógica) ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0
    status = solver.Solve(model)

    # --- PROCESAR RESULTADOS (tu lógica) ---
    placed_pieces = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for p_data in unpacked_pieces:
            p_id = p_data['id']
            is_rotated = solver.Value(rotated_vars[p_id]) if p_id in rotated_vars else False
            original_piece = original_pieces_map[p_id]
            
            placed_pieces.append({
                "id": p_id,
                "x": solver.Value(x_vars[p_id]), "y": solver.Value(y_vars[p_id]),
                "width": original_piece.width if not is_rotated else original_piece.height,
                "height": original_piece.height if not is_rotated else original_piece.width,
                "rotated": is_rotated
            })

    # --- El resto de tu código es idéntico y correcto ---
    all_placed_ids = {p['id'] for p in placed_pieces}
    impossible_ids = [p_id for p_id in original_pieces_map if p_id not in all_placed_ids]
    
    total_placed_piece_area = sum(p['width'] * p['height'] for p in placed_pieces)
    total_cut_length_mm = sum(2 * (p['width'] + p['height']) for p in placed_pieces)

    if request.material_type == 'roll':
        consumed_length = solver.ObjectiveValue()
        total_material_area = request.sheet.width * consumed_length
        final_sheet_height = consumed_length
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
    
    # NOTA: Este solver actual solo maneja 1 lámina.
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