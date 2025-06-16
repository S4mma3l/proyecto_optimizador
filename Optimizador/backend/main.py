from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import rectpack

# --- Modelos de datos y configuración de FastAPI/CORS (sin cambios) ---
class Piece(BaseModel):
    width: float
    height: float
    id: str

class Sheet(BaseModel):
    width: float
    height: float

class OptimizationRequest(BaseModel):
    sheet: Sheet
    pieces: List[Piece]
    kerf: float = 0

app = FastAPI(title="API de Optimización de Corte Iterativa", version="3.1.0")
origins = ["http://localhost", "http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    all_pieces_input = request.pieces
    sheet_width = request.sheet.width
    sheet_height = request.sheet.height
    kerf = request.kerf

    # --- Validación previa de piezas imposibles (sin cambios) ---
    placeable_pieces_models = []
    impossible_pieces_ids = []
    for piece in all_pieces_input:
        w, h = piece.width + kerf, piece.height + kerf
        can_fit = (w <= sheet_width and h <= sheet_height) or (w <= sheet_height and h <= sheet_width)
        if can_fit:
            placeable_pieces_models.append(piece)
        else:
            impossible_pieces_ids.append(piece.id)
    
    # --- LÓGICA DE EMPAQUETADO ITERATIVO (CORREGIDA) ---

    # --- CAMBIO #1: En lugar de objetos 'Rectangle', usamos diccionarios simples ---
    pieces_to_pack = [
        {'width': p.width + kerf, 'height': p.height + kerf, 'rid': p.id} 
        for p in placeable_pieces_models
    ]
    
    packed_sheets = []
    sheet_index_counter = 0

    while len(pieces_to_pack) > 0:
        sheet_index_counter += 1

        packer = rectpack.newPacker(pack_algo=rectpack.GuillotineBafLas, rotation=True)

        # --- CAMBIO #2: Añadimos los rectángulos al packer desde nuestra lista de diccionarios ---
        for piece_data in pieces_to_pack:
            packer.add_rect(width=piece_data['width'], height=piece_data['height'], rid=piece_data['rid'])
        
        packer.add_bin(width=sheet_width, height=sheet_height)
        packer.pack()

        # --- Recolectar resultados de ESTA lámina (sin cambios) ---
        placed_rects_in_this_sheet = packer[0]
        sheet_data = {
            "sheet_index": sheet_index_counter,
            "sheet_dimensions": {"width": sheet_width, "height": sheet_height},
            "placed_pieces": [],
        }
        
        sheet_area = sheet_width * sheet_height
        used_area_on_sheet = 0
        
        placed_ids_in_this_sheet = {rect.rid for rect in placed_rects_in_this_sheet}

        for rect in placed_rects_in_this_sheet:
            original_piece = next((p for p in placeable_pieces_models if p.id == rect.rid), None)
            
            piece_width_no_kerf = rect.width - kerf
            piece_height_no_kerf = rect.height - kerf

            sheet_data["placed_pieces"].append({
                "id": rect.rid, "x": rect.x, "y": rect.y,
                "width": piece_width_no_kerf, "height": piece_height_no_kerf,
                "rotated": piece_width_no_kerf != original_piece.width
            })
            used_area_on_sheet += piece_width_no_kerf * piece_height_no_kerf
        
        efficiency = (used_area_on_sheet / sheet_area) * 100 if sheet_area > 0 else 0
        sheet_data["metrics"] = {
             "used_area_sq_mm": used_area_on_sheet,
             "efficiency_percentage": round(efficiency, 2),
             "piece_count": len(placed_rects_in_this_sheet)
        }
        
        # Solo añadir la lámina si se colocó algo en ella
        if len(placed_rects_in_this_sheet) > 0:
            packed_sheets.append(sheet_data)

        # --- CAMBIO #3: Actualizamos la lista de diccionarios para la siguiente iteración ---
        pieces_to_pack = [p for p in pieces_to_pack if p['rid'] not in placed_ids_in_this_sheet]

        # Salvaguarda para evitar bucles infinitos si no se pudo colocar nada
        if len(placed_rects_in_this_sheet) == 0 and len(pieces_to_pack) > 0:
            break


    # --- Finalizar y devolver la respuesta (sin cambios) ---
    unplaced_piece_ids = [p['rid'] for p in pieces_to_pack] # Las que sobraron del bucle
    total_placed_pieces = sum(len(s['placed_pieces']) for s in packed_sheets)

    return {
        "sheets": packed_sheets,
        "impossible_to_place_ids": impossible_pieces_ids,
        "unplaced_piece_ids": unplaced_piece_ids,
        "global_metrics": {
            "total_sheets_used": sheet_index_counter,
            "total_pieces": len(all_pieces_input),
            "total_placed_pieces": total_placed_pieces,
        }
    }