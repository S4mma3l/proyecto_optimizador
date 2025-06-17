from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import rectpack

# --- MODELO DE PIEZA ACTUALIZADO ---
class Piece(BaseModel):
    width: float
    height: float
    id: str
    quantity: int = 1

class Sheet(BaseModel):
    width: float
    height: float

class OptimizationRequest(BaseModel):
    material_type: Literal["sheet", "roll"]
    sheet: Sheet
    pieces: List[Piece]
    kerf: float = 0

app = FastAPI(title="API de Optimización de Corte v6", version="6.1.0")
allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "https://s4mma3l.github.io"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def pack_on_roll(roll_width, pieces, kerf):
    placed_pieces, impossible_ids = [], []
    pieces_sorted = sorted(pieces, key=lambda p: p.height, reverse=True)
    current_x, current_y, row_height = 0, 0, 0
    
    for piece in pieces_sorted:
        width_orig, height_orig = piece.width, piece.height
        if (width_orig + kerf > roll_width) and (height_orig + kerf > roll_width):
            impossible_ids.append(piece.id)
            continue

        use_width, use_height = width_orig + kerf, height_orig + kerf
        rotated = False
        if use_width > roll_width:
             use_width, use_height = use_height, use_width
             rotated = True
        
        if current_x + use_width > roll_width:
            current_y += row_height
            current_x, row_height = 0, 0

        placed_pieces.append({
            "id": piece.id, "x": current_x, "y": current_y,
            "width": use_width - kerf, "height": use_height - kerf, "rotated": rotated
        })
        current_x += use_width
        if use_height > row_height: row_height = use_height
    
    total_consumed_length = current_y + row_height if placed_pieces else 0
    return placed_pieces, total_consumed_length, impossible_ids

@app.post("/api/optimize")
def optimize_layout(request: OptimizationRequest):
    # 1. "Desempaquetar" las piezas según la cantidad
    unpacked_pieces = []
    for piece in request.pieces:
        for i in range(piece.quantity):
            unpacked_pieces.append(Piece(id=f"{piece.id}-{i+1}" if piece.quantity > 1 else piece.id, width=piece.width, height=piece.height))

    kerf = request.kerf
    
    if request.material_type == 'roll':
        roll_width = request.sheet.width
        placed_pieces, consumed_length, impossible_ids = pack_on_roll(roll_width, unpacked_pieces, kerf)
        
        placed_ids = {p['id'] for p in placed_pieces}
        total_placed_piece_area = sum(p.width * p.height for p in unpacked_pieces if p.id in placed_ids)
        total_roll_area_used = roll_width * consumed_length if consumed_length > 0 else 0
        waste_area = total_roll_area_used - total_placed_piece_area
        waste_percentage = (waste_area / total_roll_area_used) * 100 if total_roll_area_used > 0 else 0
        
        sheet_data = {
            "sheet_index": 1,
            "sheet_dimensions": {"width": roll_width, "height": consumed_length if consumed_length > 0 else 1},
            "placed_pieces": placed_pieces,
            "metrics": {"piece_count": len(placed_pieces)}
        }
        
        return {
            "sheets": [sheet_data] if placed_pieces or impossible_ids else [],
            "impossible_to_place_ids": impossible_ids, "unplaced_piece_ids": [],
            "global_metrics": {
                "material_type": "roll",
                "total_pieces": len(unpacked_pieces),
                "total_placed_pieces": len(placed_pieces),
                "waste_percentage": round(waste_percentage, 2)
            }
        }
    else:
        sheet_width, sheet_height = request.sheet.width, request.sheet.height
        placeable_pieces_models, impossible_ids = [], []
        for p in unpacked_pieces:
            w, h = p.width + kerf, p.height + kerf
            if (w <= sheet_width and h <= sheet_height) or (w <= sheet_height and h <= sheet_width):
                placeable_pieces_models.append(p)
            else:
                impossible_ids.append(p.id)
        
        pieces_to_pack = [{'width': p.width + kerf, 'height': p.height + kerf, 'rid': p.id} for p in placeable_pieces_models]
        packed_sheets = []
        
        while pieces_to_pack:
            packer = rectpack.newPacker(pack_algo=rectpack.GuillotineBafLas, rotation=True)
            for p_data in pieces_to_pack: packer.add_rect(**p_data)
            packer.add_bin(sheet_width, sheet_height)
            packer.pack()
            placed_rects = packer[0]
            if not placed_rects: break
            
            placed_ids = {r.rid for r in placed_rects}
            sheet_data = {"sheet_index": len(packed_sheets) + 1, "sheet_dimensions": {"width": sheet_width, "height": sheet_height}, "placed_pieces": [], "metrics": {}}
            sheet_data["metrics"]["piece_count"] = len(placed_rects)
            packed_sheets.append(sheet_data)
            for r in placed_rects:
                orig_p = next((p for p in placeable_pieces_models if p.id == r.rid), None)
                pw, ph = r.width - kerf, r.height - kerf
                sheet_data["placed_pieces"].append({"id": r.rid, "x": r.x, "y": r.y, "width": pw, "height": ph, "rotated": pw != orig_p.width if orig_p else False})
            
            pieces_to_pack = [p for p in pieces_to_pack if p['rid'] not in placed_ids]
            
        unplaced_ids = [p['rid'] for p in pieces_to_pack]
        
        all_placed_ids = {p['id'] for s in packed_sheets for p in s['placed_pieces']}
        total_placed_piece_area = sum(p.width * p.height for p in unpacked_pieces if p.id in all_placed_ids)
        total_sheet_area_used = len(packed_sheets) * sheet_width * sheet_height
        waste_area = total_sheet_area_used - total_placed_piece_area
        waste_percentage = (waste_area / total_sheet_area_used) * 100 if total_sheet_area_used > 0 else 0

        return {
            "sheets": packed_sheets, "impossible_to_place_ids": impossible_ids, "unplaced_piece_ids": unplaced_ids,
            "global_metrics": {
                "material_type": "sheet", "total_sheets_used": len(packed_sheets),
                "total_pieces": len(unpacked_pieces), "total_placed_pieces": len(all_placed_ids),
                "waste_percentage": round(waste_percentage, 2)
            }
        }