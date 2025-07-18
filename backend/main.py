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
    title="API de Optimización de Corte (Refinamiento Global)",
    description="Motor con algoritmo profesional de dos fases para una perfección y estabilidad impecables.",
    version="25.0.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- FUNCIÓN HELPER PARA EMPAQUETAR EN MÚLTIPLES CONTENEDORES ---
# Esta función intenta empaquetar un conjunto de piezas en un número específico de contenedores.
def run_multi_bin_packing(pieces_to_pack, num_bins, bin_width, bin_height, kerf, rotation_allowed, algo):
    packer = rectpack.newPacker(pack_algo=algo, rotation=rotation_allowed)
    for p in pieces_to_pack:
        packer.add_rect(width=p['width'] + kerf, height=p['height'] + kerf, rid=p.get('id'))
    for _ in range(num_bins):
        packer.add_bin(width=bin_width, height=bin_height)
    packer.pack()
    # Devuelve el objeto packer completo, que contiene tanto los contenedores como las piezas no colocadas.
    return packer


@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # Desempaquetamos las piezas, igual que antes
    unpacked_pieces = [
        {"id": f"{p.id}-{i+1}" if p.quantity > 1 else p.id, "width": p.width, "height": p.height}
        for p in request.pieces for i in range(p.quantity)
    ]

    # Estrategias de ordenamiento y algoritmos
    sort_strategies = {
        "area": lambda p_list: sorted(p_list, key=lambda p: p['width'] * p['height'], reverse=True),
        "short_side": lambda p_list: sorted(p_list, key=lambda p: min(p['width'], p['height']), reverse=True),
        "long_side": lambda p_list: sorted(p_list, key=lambda p: max(p['width'], p['height']), reverse=True),
        "height": lambda p_list: sorted(p_list, key=lambda p: p['height'], reverse=True),
        "width": lambda p_list: sorted(p_list, key=lambda p: p['width'], reverse=True),
        "perimeter": lambda p_list: sorted(p_list, key=lambda p: 2 * p['width'] + 2 * p['height'], reverse=True),
        "none": lambda p_list: p_list
    }
    algos_to_test = [
        rectpack.MaxRectsBssf, rectpack.MaxRectsBaf, rectpack.MaxRectsBlsf,
        rectpack.GuillotineBssfSas, rectpack.GuillotineBafSas, rectpack.GuillotineBlsfSas
    ]

    final_bins = []

    # --- LÓGICA DE OPTIMIZACIÓN DUAL Y ROBUSTA ---
    if request.material_type == 'sheet':
        # --- FASE 1: OBTENER UNA SOLUCIÓN INICIAL DE ALTA CALIDAD ---
        print("\n--- FASE 1: Generando solución inicial de alta calidad ---")
        initial_bins = []
        pieces_to_pack = list(unpacked_pieces)
        while pieces_to_pack:
            best_bin_for_this_sheet = None
            best_selection_criteria = (-1, -1)
            for sort_name, sort_func in sort_strategies.items():
                for algo in algos_to_test:
                    try:
                        packer = rectpack.newPacker(pack_algo=algo, rotation=not request.respect_grain)
                        for p in sort_func(pieces_to_pack):
                            packer.add_rect(width=p['width'] + request.kerf, height=p['height'] + request.kerf, rid=p.get('id'))
                        packer.add_bin(width=request.sheet.width, height=request.sheet.height)
                        packer.pack()
                        current_bin = packer[0] if len(packer) > 0 else None
                        if current_bin and len(current_bin) > 0:
                            placed_area = sum((r.width - request.kerf) * (r.height - request.kerf) for r in current_bin)
                            fill_percentage = (placed_area / (current_bin.width * current_bin.height)) * 100
                            if (fill_percentage, len(current_bin)) > best_selection_criteria:
                                best_selection_criteria = (fill_percentage, len(current_bin))
                                best_bin_for_this_sheet = current_bin
                    except Exception as e:
                        print(f"ADVERTENCIA en Fase 1: {e}")
                        continue
            if best_bin_for_this_sheet:
                initial_bins.append(best_bin_for_this_sheet)
                placed_ids = {r.rid for r in best_bin_for_this_sheet}
                pieces_to_pack = [p for p in pieces_to_pack if p['id'] not in placed_ids]
            else:
                break
        
        print(f"--- FASE 1 Completa: Solución inicial encontrada con {len(initial_bins)} láminas. ---")

        # --- FASE 2: REFINAMIENTO GLOBAL PARA LA PERFECCIÓN ---
        if len(initial_bins) > 1:
            num_target_sheets = len(initial_bins) - 1
            print(f"\n--- FASE 2: Intentando refinamiento global para reducir a {num_target_sheets} láminas ---")
            best_refined_solution = None
            min_waste_refined = float('inf')
            for sort_name, sort_func in sort_strategies.items():
                for algo in algos_to_test:
                    try:
                        packer = run_multi_bin_packing(
                            sort_func(unpacked_pieces), num_target_sheets, request.sheet.width, request.sheet.height,
                            request.kerf, not request.respect_grain, algo
                        )
                        if not packer.unplaced_rects():
                            last_bin_waste = (packer[-1].width * packer[-1].height) - sum((r.width - request.kerf) * (r.height - request.kerf) for r in packer[-1])
                            if last_bin_waste < min_waste_refined:
                                min_waste_refined = last_bin_waste
                                best_refined_solution = packer
                                print(f"  -> ¡ÉXITO DE REFINAMIENTO! Solución encontrada con {num_target_sheets} láminas por '{algo.__name__}/{sort_name}'")
                    except Exception as e:
                        print(f"ADVERTENCIA en Fase 2: {e}")
                        continue
            if best_refined_solution:
                print("--- FASE 2 Completa: ¡Refinamiento exitoso! Usando la solución mejorada. ---")
                final_bins = best_refined_solution
            else:
                print("--- FASE 2 Completa: No se pudo mejorar. La solución inicial es la óptima. ---")
                final_bins = initial_bins
        else:
            final_bins = initial_bins

    elif request.material_type == 'roll':
        # --- LÓGICA PARA ROLLOS: BÚSQUEDA GLOBAL DEFINITIVA ---
        print(f"\n--- Iniciando Optimización para Rollo con {len(unpacked_pieces)} piezas ---")
        best_roll_solution = None
        best_roll_criteria = (-1, 0)
        for sort_name, sort_func in sort_strategies.items():
            for algo in algos_to_test:
                try:
                    packer = run_multi_bin_packing(
                        sort_func(unpacked_pieces), 1, request.sheet.width, 9999999,
                        request.kerf, not request.respect_grain, algo
                    )
                    current_bin = packer[0] if len(packer) > 0 else None
                    if not current_bin or len(current_bin) == 0: continue
                    placed_count = len(current_bin)
                    consumed_length = max((r.y + r.height for r in current_bin), default=0)
                    current_criteria = (placed_count, -consumed_length)
                    if current_criteria > best_roll_criteria:
                        best_roll_criteria = current_criteria
                        best_roll_solution = current_bin
                        print(f"  -> Nueva solución encontrada: {placed_count} piezas en {consumed_length:.2f}mm")
                except Exception as e:
                    print(f"ADVERTENCIA en optimización de rollo: {e}")
                    continue
        if best_roll_solution:
            final_bins.append(best_roll_solution)
        else:
            print("No se pudo encontrar una solución para el rollo.")

    # --- PROCESAMIENTO DE RESULTADOS (Unificado) ---
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