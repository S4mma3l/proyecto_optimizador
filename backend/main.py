from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import rectpack

# --- Modelos de Datos (sin cambios) ---
class Piece(BaseModel):
    width: float
    height: float
    id: str

class Sheet(BaseModel):
    width: float
    height: float

class OptimizationRequest(BaseModel):
    material_type: Literal["sheet", "roll"]
    sheet: Sheet
    pieces: List[Piece]
    kerf: float = 0

# --- Inicializar la aplicación FastAPI ---
app = FastAPI(
    title="API de Optimización - MODO DEPURACIÓN",
    description="Añadidos logs para cazar el bug del modo rollo.",
    version="5.2.2"
)

# --- Configuración de CORS (sin cambios) ---
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://s4mma3l.github.io" 
]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- ALGORITMO PARA ROLLOS CON LOGS DE DEPURACIÓN ---
def pack_on_roll(roll_width, pieces, kerf):
    placed_pieces = []
    impossible_ids = []
    
    pieces_sorted = sorted(pieces, key=lambda p: p.height, reverse=True)

    current_x = 0
    current_y = 0
    row_height = 0
    
    # --- INICIO DE LOGS ---
    print("--- INICIANDO OPTIMIZACIÓN EN MODO ROLLO ---")
    print(f"Ancho del Rollo recibido: {roll_width}, Kerf: {kerf}")
    
    for piece in pieces_sorted:
        width_orig, height_orig = piece.width, piece.height
        
        print(f"\n--- Comprobando Pieza ID: {piece.id} ---")
        print(f"Dimensiones originales (w, h): {width_orig}, {height_orig}")

        # Comprobación de imposibilidad con kerf
        check_normal_fit = (width_orig + kerf) <= roll_width
        check_rotated_fit = (height_orig + kerf) <= roll_width
        
        print(f"Comprobación NORMAL: ¿({width_orig} + {kerf}) <= {roll_width}? -> {check_normal_fit}")
        print(f"Comprobación ROTADA: ¿({height_orig} + {kerf}) <= {roll_width}? -> {check_rotated_fit}")

        is_impossible = not check_normal_fit and not check_rotated_fit
        
        print(f"Decisión: ¿Es imposible? (¿Son ambas comprobaciones 'False'?) -> {is_impossible}")

        if is_impossible:
            impossible_ids.append(piece.id)
            print(f"--> RESULTADO: Pieza {piece.id} marcada como IMPOSIBLE.")
            continue
        
        print(f"--> RESULTADO: Pieza {piece.id} es POSIBLE de colocar.")
        
        # --- Lógica de colocación ---
        use_width = width_orig + kerf
        use_height = height_orig + kerf
        rotated = False

        # Si no cabe en su orientación normal, DEBEMOS rotarla (ya sabemos que rotada sí cabe).
        if not check_normal_fit:
             use_width, use_height = use_height, use_width
             rotated = True
        
        # Si la pieza no cabe en la fila actual, empezar una nueva.
        if current_x + use_width > roll_width:
            current_y += row_height
            current_x = 0
            row_height = 0

        placed_pieces.append({
            "id": piece.id, "x": current_x, "y": current_y,
            "width": use_width - kerf, "height": use_height - kerf, "rotated": rotated
        })

        current_x += use_width
        if use_height > row_height:
            row_height = use_height
    
    total_consumed_length = current_y + row_height if placed_pieces else 0
    print("\n--- OPTIMIZACIÓN FINALIZADA ---")
    return placed_pieces, total_consumed_length, impossible_ids


# --- Endpoint de la API ---
@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # --- LÓGICA PARA MATERIALES TIPO ROLLO ---
    if request.material_type == 'roll':
        placed_pieces, consumed_length, impossible_ids = pack_on_roll(request.sheet.width, request.pieces, request.kerf)
        
        if not placed_pieces:
            consumed_length = 0

        sheet_data = {
            "sheet_index": 1,
            "sheet_dimensions": {"width": request.sheet.width, "height": consumed_length if consumed_length > 0 else 1},
            "placed_pieces": placed_pieces,
            "metrics": {"consumed_length_mm": consumed_length, "piece_count": len(placed_pieces)}
        }
        
        return {
            "sheets": [sheet_data] if placed_pieces or impossible_ids else [],
            "impossible_to_place_ids": impossible_ids,
            "unplaced_piece_ids": [],
            "global_metrics": {
                "material_type": "roll", "total_sheets_used": 1 if placed_pieces else 0,
                "total_pieces": len(request.pieces), "total_placed_pieces": len(placed_pieces)
            }
        }
    
    # --- LÓGICA COMPLETA PARA LÁMINAS ---
    else:
        all_pieces_input = request.pieces
        sheet_width = request.sheet.width
        sheet_height = request.sheet.height
        kerf = request.kerf

        placeable_pieces_models = []
        impossible_pieces_ids = []
        for piece in all_pieces_input:
            w, h = piece.width + kerf, piece.height + kerf
            can_fit = (w <= sheet_width and h <= sheet_height) or (w <= sheet_height and h <= sheet_width)
            if can_fit:
                placeable_pieces_models.append(piece)
            else:
                impossible_pieces_ids.append(piece.id)
        
        pieces_to_pack = [{'width': p.width + kerf, 'height': p.height + kerf, 'rid': p.id} for p in placeable_pieces_models]
        
        packed_sheets = []
        sheet_index_counter = 0

        while len(pieces_to_pack) > 0:
            sheet_index_counter += 1
            packer = rectpack.newPacker(pack_algo=rectpack.GuillotineBafLas, rotation=True)
            for piece_data in pieces_to_pack:
                packer.add_rect(width=piece_data['width'], height=piece_data['height'], rid=piece_data['rid'])
            packer.add_bin(width=sheet_width, height=sheet_height)
            packer.pack()

            placed_rects_in_this_sheet = packer[0]
            if not placed_rects_in_this_sheet: 
                break 
                
            sheet_data = {
                "sheet_index": sheet_index_counter,
                "sheet_dimensions": {"width": sheet_width, "height": sheet_height},
                "placed_pieces": [], "metrics": {}
            }
            
            placed_ids_in_this_sheet = {rect.rid for rect in placed_rects_in_this_sheet}
            used_area_on_sheet = 0

            for rect in placed_rects_in_this_sheet:
                original_piece = next((p for p in placeable_pieces_models if p.id == rect.rid), None)
                pw, ph = rect.width - kerf, rect.height - kerf
                sheet_data["placed_pieces"].append({
                    "id": rect.rid, "x": rect.x, "y": rect.y, "width": pw, "height": ph,
                    "rotated": pw != original_piece.width if original_piece else False
                })
                used_area_on_sheet += pw * ph
            
            efficiency = (used_area_on_sheet / (sheet_width * sheet_height)) * 100 if (sheet_width * sheet_height) > 0 else 0
            sheet_data["metrics"] = {"efficiency_percentage": round(efficiency, 2), "piece_count": len(placed_rects_in_this_sheet)}
            packed_sheets.append(sheet_data)

            pieces_to_pack = [p for p in pieces_to_pack if p['rid'] not in placed_ids_in_this_sheet]

        unplaced_piece_ids = [p['rid'] for p in pieces_to_pack]
        total_placed_pieces = sum(len(s['placed_pieces']) for s in packed_sheets)

        return {
            "sheets": packed_sheets,
            "impossible_to_place_ids": impossible_pieces_ids,
            "unplaced_piece_ids": unplaced_piece_ids,
            "global_metrics": {
                "material_type": "sheet",
                "total_sheets_used": len(packed_sheets),
                "total_pieces": len(all_pieces_input),
                "total_placed_pieces": total_placed_pieces,
            }
        }