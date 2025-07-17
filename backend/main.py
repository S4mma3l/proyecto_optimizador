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
    title="API de Optimización de Corte (Lógica Dual Perfeccionada)",
    description="Motor con algoritmos especializados y perfeccionados para láminas y rollos.",
    version="19.0.0"
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

    final_bins = []

    # --- LÓGICA DE OPTIMIZACIÓN DUAL ---
    # Se aplica una estrategia diferente si el material es 'sheet' o 'roll'.

    if request.material_type == 'sheet':
        # --- ESTRATEGIA 1: LLENADO EXHAUSTIVO PARA LÁMINAS (PERFECCIONADO) ---
        pieces_to_pack = list(unpacked_pieces)
        sheet_index = 0
        while pieces_to_pack:
            sheet_index += 1
            print(f"\n--- Optimizando Lámina #{sheet_index} con {len(pieces_to_pack)} piezas restantes ---")
            
            best_bin_for_this_sheet = None
            # Criterio de selección mejorado: (porcentaje de llenado, número de piezas)
            best_selection_criteria = (-1, -1) 
            best_strategy_info = {}

            for sort_name, sort_func in sort_strategies.items():
                sorted_pieces = sort_func(pieces_to_pack)
                for algo in algos_to_test:
                    try:
                        current_bin = run_single_bin_packing(
                            sorted_pieces, request.sheet.width, request.sheet.height,
                            request.kerf, not request.respect_grain, algo
                        )
                        if current_bin and len(current_bin) > 0:
                            placed_area = sum((r.width - request.kerf) * (r.height - request.kerf) for r in current_bin)
                            sheet_area = current_bin.width * current_bin.height
                            fill_percentage = (placed_area / sheet_area) * 100 if sheet_area > 0 else 0
                            num_placed_pieces = len(current_bin)
                            
                            # PERFECCIONAMIENTO: Se usa un criterio de desempate.
                            # Se prioriza el mayor porcentaje de llenado, y si es igual,
                            # se prefiere la solución que haya empaquetado más piezas.
                            if (fill_percentage, num_placed_pieces) > best_selection_criteria:
                                best_selection_criteria = (fill_percentage, num_placed_pieces)
                                best_bin_for_this_sheet = current_bin
                                best_strategy_info = {'sort': sort_name, 'algo': algo.__name__}
                    except Exception as e:
                        print(f"ADVERTENCIA: Falló la combinación: Orden='{sort_name}', Algo='{algo.__name__}'. Error: {e}")
                        continue
            
            if best_bin_for_this_sheet:
                fill_perc, num_pieces = best_selection_criteria
                print(f"Mejor llenado para Lámina #{sheet_index} encontrado ({fill_perc:.2f}% / {num_pieces} piezas) con: {best_strategy_info}")
                final_bins.append(best_bin_for_this_sheet)
                placed_ids = {r.rid for r in best_bin_for_this_sheet}
                pieces_to_pack = [p for p in pieces_to_pack if p['id'] not in placed_ids]
            else:
                print("No se pudieron colocar más piezas. Finalizando optimización.")
                break
    
    elif request.material_type == 'roll':
        # --- ESTRATEGIA 2: CONSUMO MÍNIMO PARA ROLLOS (NUEVA LÓGICA) ---
        print(f"\n--- Optimizando Rollo con {len(unpacked_pieces)} piezas ---")
        best_bin_for_roll = None
        min_consumed_length = float('inf')
        best_strategy_info = {}

        # Se realiza un Súper-Torneo para encontrar la combinación que use la menor longitud de rollo.
        for sort_name, sort_func in sort_strategies.items():
            sorted_pieces = sort_func(unpacked_pieces)
            for algo in algos_to_test:
                try:
                    # Se usa una altura "infinita" para simular el rollo.
                    current_bin = run_single_bin_packing(
                        sorted_pieces, request.sheet.width, 9999999,
                        request.kerf, not request.respect_grain, algo
                    )
                    if current_bin and len(current_bin) > 0:
                        consumed_length = max((r.y + r.height for r in current_bin), default=0)
                        if consumed_length < min_consumed_length:
                            min_consumed_length = consumed_length
                            best_bin_for_roll = current_bin
                            best_strategy_info = {'sort': sort_name, 'algo': algo.__name__}
                except Exception as e:
                    print(f"ADVERTENCIA: Falló la combinación: Orden='{sort_name}', Algo='{algo.__name__}'. Error: {e}")
                    continue
        
        if best_bin_for_roll:
            print(f"Mejor distribución para Rollo encontrada (largo: {min_consumed_length:.2f}mm) con: {best_strategy_info}")
            final_bins.append(best_bin_for_roll)

    # --- PROCESAMIENTO DE RESULTADOS (Unificado para ambas estrategias) ---
    packed_sheets = []
    all_placed_ids = set()
    total_placed_piece_area = 0
    total_cut_length_mm = 0
    max_y_in_roll = 0
    
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
            if request.material_type == 'roll':
                if r.y + r.height > max_y_in_roll: max_y_in_roll = r.y + r.height
        
        sheet_data["metrics"]["piece_count"] = len(abin)
        packed_sheets.append(sheet_data)

    impossible_ids = [p['id'] for p in unpacked_pieces if p['id'] not in all_placed_ids]
    
    # Calcular métricas globales
    if request.material_type == 'roll' and packed_sheets:
        consumed_length = max_y_in_roll
        # Se ajusta la altura del resultado para que coincida con el largo consumido.
        packed_sheets[0]['sheet_dimensions']['height'] = consumed_length
        total_material_area = request.sheet.width * consumed_length
    else:
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