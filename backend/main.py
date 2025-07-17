from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal, Dict
import rectpack
import math

# --- MODELOS DE DATOS (Sin cambios) ---
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

# --- CONFIGURACIÓN DE FASTAPI Y CORS (Sin cambios) ---
app = FastAPI(
    title="API de Optimización de Corte (Llenado Exhaustivo)",
    description="Motor con algoritmo de llenado exhaustivo por lámina para máxima perfección.",
    version="18.0.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- FUNCIÓN HELPER REVISADA: AHORA EMPAQUETA UNA SOLA LÁMINA ---
# La lógica de esta función se simplifica. Su única responsabilidad es intentar
# empaquetar un conjunto de piezas en UN SOLO contenedor y devolver el resultado.
def run_single_bin_packing(pieces_to_pack_data, bin_width, bin_height, kerf, rotation_allowed, algo):
    packer = rectpack.newPacker(pack_algo=algo, rotation=rotation_allowed)
    
    # Se añade el kerf a cada pieza antes de optimizar
    for p in pieces_to_pack_data:
        packer.add_rect(width=p['width'] + kerf, height=p['height'] + kerf, rid=p.get('id'))
        
    packer.add_bin(width=bin_width, height=bin_height)
    packer.pack()
    
    # Devolvemos el primer (y único) contenedor del resultado
    return packer[0] if len(packer) > 0 else None


@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # Desempaquetamos las piezas, igual que antes
    unpacked_pieces = [
        {"id": f"{p.id}-{i+1}" if p.quantity > 1 else p.id, "width": p.width, "height": p.height}
        for p in request.pieces for i in range(p.quantity)
    ]

    # Estrategias de ordenamiento y algoritmos (sin cambios)
    sort_strategies = {
        "area": lambda pieces: sorted(pieces, key=lambda p: p['width'] * p['height'], reverse=True),
        "short_side": lambda pieces: sorted(pieces, key=lambda p: min(p['width'], p['height']), reverse=True),
        "long_side": lambda pieces: sorted(pieces, key=lambda p: max(p['width'], p['height']), reverse=True),
        "height": lambda pieces: sorted(pieces, key=lambda p: p['height'], reverse=True),
        "width": lambda pieces: sorted(pieces, key=lambda p: p['width'], reverse=True),
        "perimeter": lambda pieces: sorted(pieces, key=lambda p: 2*p['width'] + 2*p['height'], reverse=True),
        "none": lambda pieces: pieces
    }
    algos_to_test = [
        rectpack.MaxRectsBssf, rectpack.MaxRectsBaf, rectpack.MaxRectsBlsf,
        rectpack.GuillotineBssfSas, rectpack.GuillotineBafSas, rectpack.GuillotineBlsfSas
    ]

    # --- LÓGICA DE OPTIMIZACIÓN PERFECCIONADA: LLENADO EXHAUSTIVO POR LÁMINA ---
    
    final_bins = []
    pieces_to_pack = list(unpacked_pieces)
    sheet_index = 0

    while pieces_to_pack:
        sheet_index += 1
        print(f"\n--- Optimizando Lámina #{sheet_index} con {len(pieces_to_pack)} piezas restantes ---")
        
        # Para cada nueva lámina, realizamos un "mini-campeonato" para encontrar el mejor llenado posible.
        best_bin_for_this_sheet = None
        best_fill_percentage = -1
        best_strategy_info = {}

        # El Súper-Torneo ahora se ejecuta DENTRO del bucle, para cada lámina.
        for sort_name, sort_func in sort_strategies.items():
            sorted_pieces = sort_func(pieces_to_pack)
            for algo in algos_to_test:
                try:
                    # Intentamos empaquetar las piezas restantes en una nueva lámina
                    current_bin = run_single_bin_packing(
                        sorted_pieces, request.sheet.width, request.sheet.height,
                        request.kerf, not request.respect_grain, algo
                    )

                    if current_bin and len(current_bin) > 0:
                        # Calculamos el área total de las piezas colocadas en esta lámina
                        placed_area = sum((r.width - request.kerf) * (r.height - request.kerf) for r in current_bin)
                        sheet_area = current_bin.width * current_bin.height
                        fill_percentage = (placed_area / sheet_area) * 100 if sheet_area > 0 else 0

                        # Si este resultado llena la lámina más que el mejor anterior, lo guardamos.
                        if fill_percentage > best_fill_percentage:
                            best_fill_percentage = fill_percentage
                            best_bin_for_this_sheet = current_bin
                            best_strategy_info = {'sort': sort_name, 'algo': algo.__name__}

                except Exception as e:
                    print(f"ADVERTENCIA: Falló la combinación: Orden='{sort_name}', Algo='{algo.__name__}'. Error: {e}")
                    continue
        
        # Si encontramos una forma de colocar al menos una pieza, la procesamos.
        if best_bin_for_this_sheet:
            print(f"Mejor llenado para Lámina #{sheet_index} encontrado ({best_fill_percentage:.2f}% de ocupación) con: {best_strategy_info}")
            final_bins.append(best_bin_for_this_sheet)
            
            # Obtenemos los IDs de las piezas que se colocaron en la lámina óptima.
            placed_ids = {r.rid for r in best_bin_for_this_sheet}
            
            # Actualizamos la lista de piezas pendientes, eliminando las que ya se colocaron.
            pieces_to_pack = [p for p in pieces_to_pack if p['id'] not in placed_ids]
        else:
            # Si no se pudo colocar ninguna pieza más, detenemos el bucle.
            print("No se pudieron colocar más piezas. Finalizando optimización.")
            break

    # --- PROCESAMIENTO DE RESULTADOS (Lógica sin cambios, ahora usa `final_bins`) ---
    packed_sheets = []
    all_placed_ids = set()
    total_placed_piece_area = 0
    total_cut_length_mm = 0
    
    for i, abin in enumerate(final_bins):
        if not abin: continue
        sheet_data = {"sheet_index": i + 1, "sheet_dimensions": {"width": abin.width, "height": abin.height}, "placed_pieces": [], "metrics": {}}
        for r in abin:
            all_placed_ids.add(r.rid)
            
            pw, ph = r.width - request.kerf, r.height - request.kerf
            original_piece = next((p for p in unpacked_pieces if p['id'] == r.rid), None)
            
            is_rotated = False
            if original_piece and not request.respect_grain:
                if (abs(pw - original_piece['width']) > 0.01 or abs(ph - original_piece['height']) > 0.01):
                    is_rotated = True

            sheet_data["placed_pieces"].append({"id": r.rid, "x": r.x, "y": r.y, "width": pw, "height": ph, "rotated": is_rotated})
            total_placed_piece_area += pw * ph
            total_cut_length_mm += 2 * (pw + ph)
        
        sheet_data["metrics"]["piece_count"] = len(abin)
        packed_sheets.append(sheet_data)

    impossible_ids = [p['id'] for p in unpacked_pieces if p['id'] not in all_placed_ids]
    
    # Calcular métricas globales
    total_material_area = len(packed_sheets) * request.sheet.width * request.sheet.height
        
    waste_percentage = ((total_material_area - total_placed_piece_area) / total_material_area) * 100 if total_material_area > 0 else 0
    total_material_area_sqm = total_material_area / 1_000_000
    
    num_passes = math.ceil(request.sheet_thickness_mm / request.cut_depth_per_pass_mm) if request.sheet_thickness_mm > 0 and request.cut_depth_per_pass_mm > 0 else 1
    total_path_distance = total_cut_length_mm * num_passes
    estimated_time_seconds = total_path_distance / request.cutting_speed_mms if request.cutting_speed_mms > 0 else 0
    
    return {
        "sheets": packed_sheets,
        "impossible_to_place_ids": impossible_ids,
        "unplaced_piece_ids": [],
        "global_metrics": {
            "material_type": request.material_type,
            "total_sheets_used": len(packed_sheets),
            "total_pieces": len(unpacked_pieces),
            "total_placed_pieces": len(all_placed_ids),
            "waste_percentage": round(waste_percentage, 2),
            "total_material_area_sqm": round(total_material_area_sqm, 2),
            "estimated_time_seconds": round(estimated_time_seconds)
        }
    }
