from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import rectpack

# --- MODELOS DE DATOS (CON cutting_speed AÑADIDO) ---
class Piece(BaseModel):
    id: str; width: float; height: float; quantity: int = 1
class Sheet(BaseModel):
    width: float; height: float
class OptimizationRequest(BaseModel):
    material_type: Literal["sheet", "roll"]
    sheet: Sheet
    pieces: List[Piece]
    kerf: float = 0
    respect_grain: bool = False
    cutting_speed: float = 50.0 # Velocidad en mm/s

# --- CONFIGURACIÓN DE FASTAPI Y CORS ---
app = FastAPI(
    title="API de Optimización de Corte v10 - Final y Completa",
    description="Versión final con todas las métricas, incluyendo tiempo de corte.",
    version="10.0.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- FUNCIÓN HELPER PARA EL TORNEO (sin cambios) ---
def run_one_packing_algorithm(unpacked_pieces_data, material_type, sheet_width, sheet_height, kerf, rotation_allowed, algo):
    pieces_to_pack = [{'width': p.width + kerf, 'height': p.height + kerf, 'rid': p.id} for p in unpacked_pieces_data]
    all_bins = []
    if material_type == 'roll':
        packer = rectpack.newPacker(pack_algo=algo, rotation=rotation_allowed)
        for p_data in pieces_to_pack: packer.add_rect(**p_data)
        packer.add_bin(width=sheet_width, height=9999999)
        packer.pack()
        all_bins.extend(packer)
    else:
        while pieces_to_pack:
            packer = rectpack.newPacker(pack_algo=algo, rotation=rotation_allowed)
            for p_data in pieces_to_pack: packer.add_rect(**p_data)
            packer.add_bin(width=sheet_width, height=sheet_height)
            packer.pack()
            if len(packer) > 0 and packer[0]:
                all_bins.append(packer[0])
                placed_ids = {r.rid for r in packer[0]}
                if not placed_ids: break
                pieces_to_pack = [p for p in pieces_to_pack if p['rid'] not in placed_ids]
            else:
                break
    if material_type == 'roll':
        max_y = 0
        if all_bins and all_bins[0]:
            for r in all_bins[0]:
                if r.y + r.height > max_y: max_y = r.y + r.height
        score = {'consumed_length': max_y}
    else:
        num_sheets = len(all_bins)
        waste = 0
        if num_sheets > 0:
            last_bin = all_bins[-1]
            total_area = sum(r.width * r.height for r in last_bin)
            waste = (last_bin.width * last_bin.height) - total_area
        score = {'sheets_used': num_sheets, 'waste_on_last': waste}
    return {'bins': all_bins, 'score': score}


@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    unpacked_pieces = [Piece(id=f"{p.id}-{i+1}" if p.quantity > 1 else p.id, width=p.width, height=p.height) for p in request.pieces for i in range(p.quantity)]
    algos_to_test = [rectpack.MaxRectsBssf, rectpack.MaxRectsBaf, rectpack.MaxRectsBlsf, rectpack.GuillotineBssfSas]
    all_results = [run_one_packing_algorithm(unpacked_pieces, request.material_type, request.sheet.width, request.sheet.height, request.kerf, not request.respect_grain, algo) for algo in algos_to_test]

    if request.material_type == 'roll':
        best_result = min(all_results, key=lambda r: r['score']['consumed_length'])
    else:
        best_result = min(all_results, key=lambda r: (r['score']['sheets_used'], r['score']['waste_on_last']))
    
    winner_bins = best_result['bins']
    packed_sheets, all_placed_ids, total_placed_piece_area, max_y_in_roll = [], set(), 0, 0
    
    # --- INICIALIZAR LONGITUD DE CORTE ---
    total_cut_length_mm = 0

    for i, abin in enumerate(winner_bins):
        if not abin: continue
        sheet_data = {"sheet_index": i + 1, "sheet_dimensions": {"width": abin.width, "height": abin.height}, "placed_pieces": [], "metrics": {}}
        for r in abin:
            all_placed_ids.add(r.rid)
            pw, ph = r.width - request.kerf, r.height - request.kerf
            original_piece = next((p for p in unpacked_pieces if p.id == r.rid), None)
            is_rotated = (pw != original_piece.width) if original_piece and not request.respect_grain else False
            sheet_data["placed_pieces"].append({"id": r.rid, "x": r.x, "y": r.y, "width": pw, "height": ph, "rotated": is_rotated})
            total_placed_piece_area += pw * ph
            
            # --- SUMAR EL PERÍMETRO DE CADA PIEZA ---
            total_cut_length_mm += 2 * (pw + ph)
            
            if r.y + r.height > max_y_in_roll: max_y_in_roll = r.y + r.height
        sheet_data["metrics"]["piece_count"] = len(abin)
        packed_sheets.append(sheet_data)

    impossible_ids = [p.id for p in unpacked_pieces if p.id not in all_placed_ids]
    
    if request.material_type == 'roll' and packed_sheets:
        consumed_length = max_y_in_roll
        packed_sheets[0]['sheet_dimensions']['height'] = consumed_length if consumed_length > 0 else 1
        total_material_area = request.sheet.width * consumed_length
    else:
        total_material_area = len(packed_sheets) * request.sheet.width * request.sheet.height
        
    waste_percentage = ((total_material_area - total_placed_piece_area) / total_material_area) * 100 if total_material_area > 0 else 0
    total_material_area_sqm = total_material_area / 1_000_000
    
    # --- CALCULAR EL TIEMPO DE CORTE ---
    cutting_time_seconds = total_cut_length_mm / request.cutting_speed if request.cutting_speed > 0 else 0

    return {
        "sheets": packed_sheets, "impossible_to_place_ids": impossible_ids, "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type, "total_sheets_used": len(packed_sheets),
            "total_pieces": len(unpacked_pieces), "total_placed_pieces": len(all_placed_ids),
            "waste_percentage": round(waste_percentage, 2),
            "total_material_area_sqm": round(total_material_area_sqm, 2),
            "cutting_time_seconds": round(cutting_time_seconds) # ¡CORRECTAMENTE AÑADIDO!
        }
    }
