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
    title="API de Optimización de Corte (Algoritmo Corregido y Estable)",
    description="Motor con Súper-Torneo de algoritmos y ordenamiento para máxima eficiencia.",
    version="17.3.0"
)
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- FUNCIÓN HELPER PARA EL TORNEO DE ALGORITMOS RECTPACK (Sin cambios en su lógica interna) ---
# Esta función sigue siendo la responsable de ejecutar UNA prueba de empaquetado.
# Ahora será llamada muchas más veces por la lógica principal.
def run_one_packing_algorithm(unpacked_pieces_data, material_type, sheet_width, sheet_height, kerf, rotation_allowed, algo):
    # --- LÓGICA DE KERF CORRECTA: Se suma el kerf a cada pieza antes de optimizar ---
    pieces_to_pack = [{'width': p['width'] + kerf, 'height': p['height'] + kerf, 'rid': p.get('id')} for p in unpacked_pieces_data]
    
    all_bins = []
    
    if material_type == 'roll':
        packer = rectpack.newPacker(pack_algo=algo, rotation=rotation_allowed)
        for p_data in pieces_to_pack: packer.add_rect(**p_data)
        packer.add_bin(width=sheet_width, height=9999999) # Altura "infinita" para rollos
        packer.pack()
        all_bins.extend(packer)
    else:
        # Lógica iterativa para láminas
        while pieces_to_pack:
            packer = rectpack.newPacker(pack_algo=algo, rotation=rotation_allowed)
            # Añadimos solo las piezas que aún no se han colocado
            for p_data in pieces_to_pack: packer.add_rect(**p_data)
            packer.add_bin(width=sheet_width, height=sheet_height)
            packer.pack()
            
            # Verificamos si la lámina actual contiene alguna pieza
            if len(packer) > 0 and len(packer[0]) > 0:
                all_bins.append(packer[0])
                # Obtenemos los IDs de las piezas que SÍ se colocaron en esta lámina
                placed_ids = {r.rid for r in packer[0]}
                if not placed_ids: break # Si no se pudo colocar ninguna pieza, detenemos el bucle
                # Actualizamos la lista de piezas a colocar, eliminando las que ya se asignaron
                pieces_to_pack = [p for p in pieces_to_pack if p['rid'] not in placed_ids]
            else:
                # Si el packer no pudo colocar ninguna pieza en una nueva lámina, paramos.
                break
    
    # Calcular el "score" para este resultado
    if material_type == 'roll':
        max_y = max((r.y + r.height for r in all_bins[0]), default=0) if all_bins and all_bins[0] else 0
        score = {'consumed_length': max_y}
    else:
        num_sheets = len(all_bins)
        waste = 0
        # Calcular el desperdicio solo en la última lámina para una mejor comparación
        if num_sheets > 0:
            last_bin = all_bins[-1]
            total_area_of_pieces_in_bin = sum((r.width - kerf) * (r.height - kerf) for r in last_bin)
            waste = (last_bin.width * last_bin.height) - total_area_of_pieces_in_bin
        score = {'sheets_used': num_sheets, 'waste_on_last': waste}

    # Devolvemos los contenedores (bins), el score y también el algoritmo y la estrategia de ordenamiento usados
    return {'bins': all_bins, 'score': score}


@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # Desempaquetamos las piezas según su cantidad, igual que antes
    unpacked_pieces = [
        {"id": f"{p.id}-{i+1}" if p.quantity > 1 else p.id, "width": p.width, "height": p.height}
        for p in request.pieces for i in range(p.quantity)
    ]

    # --- MEJORA 1: ESTRATEGIAS DE ORDENAMIENTO ---
    sort_strategies = {
        "area": lambda pieces: sorted(pieces, key=lambda p: p['width'] * p['height'], reverse=True),
        "short_side": lambda pieces: sorted(pieces, key=lambda p: min(p['width'], p['height']), reverse=True),
        "long_side": lambda pieces: sorted(pieces, key=lambda p: max(p['width'], p['height']), reverse=True),
        "height": lambda pieces: sorted(pieces, key=lambda p: p['height'], reverse=True),
        "width": lambda pieces: sorted(pieces, key=lambda p: p['width'], reverse=True),
        "perimeter": lambda pieces: sorted(pieces, key=lambda p: 2*p['width'] + 2*p['height'], reverse=True),
        "none": lambda pieces: pieces
    }

    # --- MEJORA 2: TORNEO DE ALGORITMOS (ESTABLE) ---
    # Se eliminan los algoritmos Skyline que causaban el error "AttributeError"
    # en el entorno de despliegue para garantizar la estabilidad.
    algos_to_test = [
        rectpack.MaxRectsBssf, rectpack.MaxRectsBaf, rectpack.MaxRectsBlsf,
        rectpack.GuillotineBssfSas, rectpack.GuillotineBafSas, rectpack.GuillotineBlsfSas
    ]

    all_results = []
    
    # --- MEJORA 3: EL "SÚPER-TORNEO" ---
    print(f"Iniciando Súper-Torneo: {len(sort_strategies)} estrategias x {len(algos_to_test)} algoritmos...")
    for sort_name, sort_func in sort_strategies.items():
        sorted_pieces = sort_func(unpacked_pieces)
        for algo in algos_to_test:
            # --- Bloque try-except para robustez ---
            try:
                result = run_one_packing_algorithm(
                    sorted_pieces, request.material_type, request.sheet.width, request.sheet.height,
                    request.kerf, not request.respect_grain, algo
                )
                # Guardamos información extra para poder depurar y saber qué combinación ganó
                result['sort_strategy'] = sort_name
                result['pack_algo'] = algo.__name__
                all_results.append(result)
            except Exception as e:
                # Si una combinación falla, se imprime un error en la consola y se continúa
                print(f"ADVERTENCIA: Falló la combinación: Orden='{sort_name}', Algo='{algo.__name__}'. Error: {e}")
                continue
    print("Súper-Torneo finalizado. Seleccionando el mejor resultado.")

    # Determinar el ganador
    if not all_results:
        return {"error": "No se pudo generar ninguna distribución válida. Verifique las dimensiones de las piezas y la lámina."}

    if request.material_type == 'roll':
        best_result = min(all_results, key=lambda r: r['score']['consumed_length'])
    else:
        best_result = min(all_results, key=lambda r: (r['score']['sheets_used'], r['score']['waste_on_last']))
    
    print(f"Mejor resultado encontrado con: Ordenamiento='{best_result['sort_strategy']}', Algoritmo='{best_result['pack_algo']}'")
    
    winner_bins = best_result['bins']
    
    # --- PROCESAMIENTO DE RESULTADOS (Sin cambios funcionales) ---
    packed_sheets = []
    all_placed_ids = set()
    total_placed_piece_area = 0
    total_cut_length_mm = 0
    max_y_in_roll = 0

    for i, abin in enumerate(winner_bins):
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
            if r.y + r.height > max_y_in_roll: max_y_in_roll = r.y + r.height
        
        sheet_data["metrics"]["piece_count"] = len(abin)
        packed_sheets.append(sheet_data)

    impossible_ids = [p['id'] for p in unpacked_pieces if p['id'] not in all_placed_ids]
    
    # Calcular métricas globales
    if request.material_type == 'roll' and packed_sheets:
        consumed_length = max_y_in_roll
        packed_sheets[0]['sheet_dimensions']['height'] = consumed_length if consumed_length > 0 else 1
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
            "estimated_time_seconds": round(estimated_time_seconds),
            "winning_strategy": {
                "sort_strategy": best_result['sort_strategy'],
                "pack_algo": best_result['pack_algo']
            }
        }
    }