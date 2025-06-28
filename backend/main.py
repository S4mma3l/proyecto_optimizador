from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import rectpack

# --- MODELOS DE DATOS (sin cambios) ---
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

# --- CONFIGURACIÓN DE FASTAPI Y CORS (sin cambios) ---
app = FastAPI(
    title="API de Optimización de Corte v8 - Hyper-Optimization",
    description="API con 'torneo de algoritmos' para resultados superiores.",
    version="8.0.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- FUNCIÓN HELPER PARA EL TORNEO ---
def run_one_packing_algorithm(unpacked_pieces, material_type, sheet_width, sheet_height, kerf, rotation_allowed, algo):
    packer = rectpack.newPacker(pack_algo=algo, rotation=rotation_allowed)
    
    for p in unpacked_pieces:
        packer.add_rect(width=p.width + kerf, height=p.height + kerf, rid=p.id)

    if material_type == 'roll':
        packer.add_bin(width=sheet_width, height=9999999)
    else:
        packer.add_bin(width=sheet_width, height=sheet_height)
        
    packer.pack()
    
    # Calcular el "score" para este resultado
    if material_type == 'roll':
        max_y = 0
        if packer and packer[0]:
            for r in packer[0]:
                if r.y + r.height > max_y:
                    max_y = r.y + r.height
        score = {'consumed_length': max_y}
    else:
        num_sheets = len(packer)
        waste = 0
        if num_sheets > 0:
            last_bin = packer[num_sheets - 1]
            total_area = sum(r.width * r.height for r in last_bin)
            waste = (last_bin.width * last_bin.height) - total_area
        score = {'sheets_used': num_sheets, 'waste_on_last': waste}

    return {'packer': packer, 'score': score}


@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # 1. Desempaquetar piezas
    unpacked_pieces = [Piece(id=f"{p.id}-{i+1}" if p.quantity > 1 else p.id, width=p.width, height=p.height)
                       for p in request.pieces for i in range(p.quantity)]

    # --- INICIO DEL TORNEO DE ALGORITMOS ---
    algos_to_test = [
        rectpack.MaxRectsBssf, # Best Short Side Fit
        rectpack.MaxRectsBaf,  # Best Area Fit
        rectpack.MaxRectsBlsf, # Best Long Side Fit
        rectpack.GuillotineBssfSas, # Guillotine Best Short Side Fit, Shorter Axis Split
    ]

    all_results = []
    for algo in algos_to_test:
        result = run_one_packing_algorithm(
            unpacked_pieces, request.material_type, request.sheet.width, request.sheet.height,
            request.kerf, not request.respect_grain, algo
        )
        all_results.append(result)

    # --- DETERMINAR EL GANADOR ---
    if request.material_type == 'roll':
        # Para rollos, el mejor es el que tiene la menor longitud consumida
        best_result = min(all_results, key=lambda r: r['score']['consumed_length'])
    else:
        # Para láminas, el mejor es el que usa menos láminas, y luego el con menos desperdicio en la última
        best_result = min(all_results, key=lambda r: (r['score']['sheets_used'], r['score']['waste_on_last']))
    
    winner_packer = best_result['packer']

    # --- 5. PROCESAR EL RESULTADO DEL GANADOR ---
    packed_sheets, all_placed_ids, total_placed_piece_area, max_y_in_roll = [], set(), 0, 0

    for i, abin in enumerate(winner_packer):
        if not abin: continue
        sheet_data = {"sheet_index": len(packed_sheets) + 1, "sheet_dimensions": {"width": abin.width, "height": abin.height}, "placed_pieces": [], "metrics": {}}
        for r in abin:
            all_placed_ids.add(r.rid)
            pw, ph = r.width - request.kerf, r.height - request.kerf
            original_piece = next((p for p in unpacked_pieces if p.id == r.rid), None)
            is_rotated = (pw != original_piece.width) if original_piece and not request.respect_grain else False
            sheet_data["placed_pieces"].append({"id": r.rid, "x": r.x, "y": r.y, "width": pw, "height": ph, "rotated": is_rotated})
            total_placed_piece_area += pw * ph
            if r.y + r.height > max_y_in_roll: max_y_in_roll = r.y + r.height
        sheet_data["metrics"]["piece_count"] = len(abin)
        packed_sheets.append(sheet_data)

    impossible_ids = [p.id for p in unpacked_pieces if p.id not in all_placed_ids]
    
    # --- 6. CALCULAR MÉTRICAS GLOBALES DEL GANADOR ---
    if request.material_type == 'roll' and packed_sheets:
        consumed_length = max_y_in_roll
        packed_sheets[0]['sheet_dimensions']['height'] = consumed_length if consumed_length > 0 else 1
        total_material_area = request.sheet.width * consumed_length
        waste_percentage = ((total_material_area - total_placed_piece_area) / total_material_area) * 100 if total_material_area > 0 else 0
    else:
        total_material_area = len(packed_sheets) * request.sheet.width * request.sheet.height
        waste_percentage = ((total_material_area - total_placed_piece_area) / total_material_area) * 100 if total_material_area > 0 else 0

    return {
        "sheets": packed_sheets,
        "impossible_to_place_ids": impossible_ids,
        "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type,
            "total_sheets_used": len(packed_sheets),
            "total_pieces": len(unpacked_pieces),
            "total_placed_pieces": len(all_placed_ids),
            "waste_percentage": round(waste_percentage, 2)
        }
    }