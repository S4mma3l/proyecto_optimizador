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
    title="API de Optimización de Corte con Google OR-Tools v13",
    description="Solver de máxima densidad con correcciones lógicas para láminas y rollos.",
    version="13.0.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # 1. Desempaquetar piezas y añadir kerf
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
    sheet_height_limit = sum(p['height'] for p in unpacked_pieces) if request.material_type == 'roll' else int(request.sheet.height)
    rotation_allowed = not request.respect_grain
    
    model = cp_model.CpModel()

    # --- VARIABLES MEJORADAS ---
    x_vars = {p['id']: model.NewIntVar(0, sheet_width, f"x_{p['id']}") for p in unpacked_pieces}
    y_vars = {p['id']: model.NewIntVar(0, sheet_height_limit, f"y_{p['id']}") for p in unpacked_pieces}
    
    x_intervals = {}
    y_intervals = {}
    rotated_vars = {} # Para almacenar la decisión de rotación del solver

    for p in unpacked_pieces:
        p_id = p['id']
        width, height = p['width'], p['height']
        
        if rotation_allowed and width != height:
            # Si se permite la rotación, creamos dos conjuntos de intervalos opcionales
            # is_rotated es una variable booleana que el solver decidirá
            is_rotated = model.NewBoolVar(f"rotated_{p_id}")
            rotated_vars[p_id] = is_rotated

            # Intervalos para la orientación original (si NO está rotada)
            x_intervals[p_id] = model.NewOptionalIntervalVar(x_vars[p_id], width, x_vars[p_id] + width, is_rotated.Not(), f"xi_{p_id}")
            y_intervals[p_id] = model.NewOptionalIntervalVar(y_vars[p_id], height, y_vars[p_id] + height, is_rotated.Not(), f"yi_{p_id}")

            # Intervalos para la orientación rotada (si SÍ está rotada)
            x_intervals[f"{p_id}_rot"] = model.NewOptionalIntervalVar(x_vars[p_id], height, x_vars[p_id] + height, is_rotated, f"xi_rot_{p_id}")
            y_intervals[f"{p_id}_rot"] = model.NewOptionalIntervalVar(y_vars[p_id], width, y_vars[p_id] + width, is_rotated, f"yi_rot_{p_id}")
        else:
            # Si no se permite rotación, creamos intervalos normales obligatorios
            x_intervals[p_id] = model.NewIntervalVar(x_vars[p_id], width, x_vars[p_id] + width, f"xi_{p_id}")
            y_intervals[p_id] = model.NewIntervalVar(y_vars[p_id], height, y_vars[p_id] + height, f"yi_{p_id}")

    # --- RESTRICCIONES CORREGIDAS ---
    # 1. No solapamiento: Esta restricción ahora maneja correctamente los intervalos opcionales
    model.AddNoOverlap2D(list(x_intervals.values()), list(y_intervals.values()))

    # 2. Límites del contenedor: Usar EndExpr() es la forma robusta
    for interval in x_intervals.values():
        model.Add(interval.EndExpr() <= sheet_width)
    for interval in y_intervals.values():
        if request.material_type == 'sheet':
            model.Add(interval.EndExpr() <= sheet_height_limit)

    # --- OBJETIVO: MINIMIZAR LA ALTURA TOTAL ---
    max_height_var = model.NewIntVar(0, sheet_height_limit, 'max_height')
    for p_id in unpacked_pieces:
        # La altura final de una pieza es su y_var más la altura del intervalo que esté activo
        # Si la pieza puede rotar, debemos considerar ambas posibilidades
        if f"{p_id['id']}_rot" in y_intervals:
            model.Add(max_height_var >= y_intervals[p_id['id']].EndExpr()).OnlyEnforceIf(rotated_vars[p_id['id']].Not())
            model.Add(max_height_var >= y_intervals[f"{p_id['id']}_rot"].EndExpr()).OnlyEnforceIf(rotated_vars[p_id['id']])
        else:
            model.Add(max_height_var >= y_intervals[p_id['id']].EndExpr())
            
    model.Minimize(max_height_var)
    
    # --- RESOLVER EL PROBLEMA ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 25.0
    status = solver.Solve(model)

    # --- PROCESAR RESULTADOS ---
    placed_pieces = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for p_data in unpacked_pieces:
            p_id = p_data['id']
            # Para que una pieza se considere colocada, su intervalo X debe estar activo
            if solver.BooleanValue(x_intervals[p_id].IsPresent()):
                original_piece = original_pieces_map[p_id]
                is_rotated = False
                
                # Si la pieza fue rotada, obtenemos sus dimensiones rotadas
                if f"{p_id}_rot" in x_intervals and solver.BooleanValue(x_intervals[f"{p_id}_rot"].IsPresent()):
                    is_rotated = True
                
                placed_pieces.append({
                    "id": p_id,
                    "x": solver.Value(x_vars[p_id]),
                    "y": solver.Value(y_vars[p_id]),
                    "width": original_piece.width if not is_rotated else original_piece.height,
                    "height": original_piece.height if not is_rotated else original_piece.width,
                    "rotated": is_rotated
                })

    all_placed_ids = {p['id'] for p in placed_pieces}
    impossible_ids = [p_id for p_id in original_pieces_map if p_id not in all_placed_ids]
    
    total_placed_piece_area = sum(p['width'] * p['height'] for p in placed_pieces)
    total_cut_length_mm = sum(2 * (p['width'] + p['height']) for p in placed_pieces)

    if request.material_type == 'roll':
        consumed_length = solver.ObjectiveValue()
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
    
    # NOTA: Este solver actual solo maneja 1 lámina. La lógica de múltiples láminas con OR-Tools es mucho más compleja.
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