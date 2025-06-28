from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import rectpack

# --- MODELOS DE DATOS (sin cambios) ---
class Piece(BaseModel):
    id: str; width: float; height: float; quantity: int = 1
class Sheet(BaseModel):
    width: float; height: float
class OptimizationRequest(BaseModel):
    material_type: Literal["sheet", "roll"]; sheet: Sheet; pieces: List[Piece]; kerf: float = 0; respect_grain: bool = False

# --- CONFIGURACIÓN DE FASTAPI Y CORS (sin cambios) ---
app = FastAPI(
    title="API de Optimización de Corte v11 - Hyper-Optimization Exhaustiva",
    description="API con torneo de combinaciones de algoritmos y heurísticas.",
    version="11.0.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- FUNCIÓN HELPER PARA EL TORNEO (ACTUALIZADA) ---
def run_one_packing_combination(unpacked_pieces_data, material_type, sheet_width, sheet_height, kerf, rotation_allowed, pack_algo, sort_algo):
    
    # Crear un packer para esta combinación específica
    packer = rectpack.newPacker(
        pack_algo=pack_algo,
        sort_algo=sort_algo,
        rotation=rotation_allowed
    )
    
    # Añadir todas las piezas
    for p in unpacked_pieces_data:
        packer.add_rect(width=p.width + kerf, height=p.height + kerf, rid=p.id)

    # Añadir los "bins"
    if material_type == 'roll':
        packer.add_bin(width=sheet_width, height=9999999)
        packer.pack()
        return {'bins': list(packer), 'score': {'consumed_length': max((r.y + r.height for r in packer[0]), default=0)}}
    else:
        # Lógica iterativa para láminas
        all_bins = []
        pieces_to_pack = list(unpacked_pieces_data)
        while pieces_to_pack:
            # En cada iteración, creamos un nuevo packer solo con las piezas restantes
            iter_packer = rectpack.newPacker(pack_algo=pack_algo, sort_algo=sort_algo, rotation=rotation_allowed)
            for p in pieces_to_pack:
                iter_packer.add_rect(width=p.width + kerf, height=p.height + kerf, rid=p.id)
            iter_packer.add_bin(width=sheet_width, height=sheet_height)
            iter_packer.pack()
            
            if not iter_packer[0]: break
            all_bins.append(iter_packer[0])
            placed_ids = {r.rid for r in iter_packer[0]}
            pieces_to_pack = [p for p in pieces_to_pack if p.id not in placed_ids]
            
        # Calcular score para láminas
        num_sheets = len(all_bins)
        last_bin_waste = 0
        if num_sheets > 0:
            last_bin = all_bins[-1]
            last_bin_waste = (last_bin.width * last_bin.height) - sum(r.width * r.height for r in last_bin)
        return {'bins': all_bins, 'score': {'sheets_used': num_sheets, 'waste_on_last': last_bin_waste}}


@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    unpacked_pieces = [Piece(id=f"{p.id}-{i+1}" if p.quantity > 1 else p.id, width=p.width, height=p.height)
                       for p in request.pieces for i in range(p.quantity)]

    # --- INICIO DEL TORNEO EXHAUSTIVO ---
    # Definimos las combinaciones de algoritmos y heurísticas a probar
    combinations_to_test = [
        {'pack_algo': rectpack.MaxRectsBssf, 'sort_algo': rectpack.SORT_AREA},
        {'pack_algo': rectpack.MaxRectsBssf, 'sort_algo': rectpack.SORT_SSIDE},
        {'pack_algo': rectpack.MaxRectsBlsf, 'sort_algo': rectpack.SORT_LSIDE},
        {'pack_algo': rectpack.MaxRectsBaf, 'sort_algo': rectpack.SORT_AREA},
        {'pack_algo': rectpack.GuillotineBssfLas, 'sort_algo': rectpack.SORT_AREA},
        {'pack_algo': rectpack.GuillotineBlsfSas, 'sort_algo': rectpack.SORT_LSIDE},
    ]

    all_results = [run_one_packing_combination(
        unpacked_pieces, request.material_type, request.sheet.width, request.sheet.height,
        request.kerf, not request.respect_grain, **combo
    ) for combo in combinations_to_test]

    # --- DETERMINAR EL GANADOR ---
    if request.material_type == 'roll':
        best_result = min(all_results, key=lambda r: r['score']['consumed_length'])
    else:
        best_result = min(all_results, key=lambda r: (r['score']['sheets_used'], r['score']['waste_on_last']))
    
    winner_bins = best_result['bins']
    
    # --- PROCESAR Y DEVOLVER EL MEJOR RESULTADO ---
    packed_sheets, all_placed_ids, total_placed_piece_area, max_y_in_roll = [], set(), 0, 0

    for i, abin in enumerate(winner_bins):
        if not abin: continue
        sheet_data = {"sheet_index": i + 1, "sheet_dimensions": {"width": abin.width, "height": abin.height}, "placed_pieces": [], "metrics": {}}
        for r in abin:
            all_placed_ids.add(r.rid)
            pw, ph = r.width - request.kerf, r.height - request.kerf
            
            # Lógica de rotación corregida y más precisa
            original_piece = next((p for p in unpacked_pieces if p.id == r.rid), None)
            is_rotated = False
            if original_piece and not request.respect_grain:
                # Compara dimensiones con/sin kerf para ser preciso
                if (r.width != original_piece.width + request.kerf) or \
                   (r.height != original_piece.height + request.kerf):
                    is_rotated = True

            sheet_data["placed_pieces"].append({"id": r.rid, "x": r.x, "y": r.y, "width": pw, "height": ph, "rotated": is_rotated})
            total_placed_piece_area += pw * ph
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

    return {
        "sheets": packed_sheets,
        "impossible_to_place_ids": impossible_ids,
        "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type, "total_sheets_used": len(packed_sheets),
            "total_pieces": len(unpacked_pieces), "total_placed_pieces": len(all_placed_ids),
            "waste_percentage": round(waste_percentage, 2),
            "total_material_area_sqm": round(total_material_area_sqm, 2)
        }
    }