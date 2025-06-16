import React, { useState, useRef } from 'react';
import { FaRulerCombined, FaTh, FaPlus, FaTrash, FaCogs, FaFileExcel } from 'react-icons/fa';
import * as XLSX from 'xlsx';

function InputForm({ onSubmit, isLoading }) {
  const [sheetWidth, setSheetWidth] = useState(2440);
  const [sheetHeight, setSheetHeight] = useState(1220);
  const [kerf, setKerf] = useState(3);
  const [pieces, setPieces] = useState([{ id: 'P1', width: 600, height: 400 }]);
  
  // --- NUEVO: Ref para el input de archivo oculto ---
  const fileInputRef = useRef(null);

  const handleAddPiece = () => {
    const newId = `P${pieces.length + 1}`;
    setPieces([...pieces, { id: newId, width: '', height: '' }]);
  };

  const handleRemovePiece = (indexToRemove) => {
    setPieces(pieces.filter((_, index) => index !== indexToRemove));
  };

  const handlePieceChange = (index, field, value) => {
    const newPieces = [...pieces];
    newPieces[index] = { ...newPieces[index], [field]: value };
    setPieces(newPieces);
  };

  // --- NUEVO: Manejador para el cambio de archivo ---
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const data = event.target.result;
        const workbook = XLSX.read(data, { type: 'binary' });
        const sheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[sheetName];
        const json = XLSX.utils.sheet_to_json(worksheet);

        if (json.length === 0) {
          alert("El archivo de Excel está vacío o tiene un formato incorrecto.");
          return;
        }

        const newPieces = [];
        let pieceCounter = 1;

        json.forEach((row, rowIndex) => {
          // Mapeo flexible de columnas (case-insensitive)
          const id = row.ID || row.id || row.Id || `Pieza-${rowIndex + 1}`;
          const width = row.width || row.ancho || row.ANCHO;
          const height = row.height || row.alto || row.ALTO;
          const quantity = row.Cant || row.cant || row.Cantidad || row.cantidad || 1;

          if (width && height) {
            for (let i = 0; i < quantity; i++) {
              // Asegurar ID único si la cantidad es > 1
              const uniqueId = quantity > 1 ? `${id}-${i + 1}` : id;
              newPieces.push({
                id: uniqueId,
                width: Number(width),
                height: Number(height),
              });
              pieceCounter++;
            }
          }
        });
        
        // Reemplazar la lista actual con las piezas del Excel
        setPieces(newPieces);
        alert(`${newPieces.length} piezas cargadas exitosamente desde el archivo.`);

      } catch (error) {
        console.error("Error al procesar el archivo de Excel", error);
        alert("Ocurrió un error al leer el archivo. Asegúrate de que tenga el formato correcto.");
      }
    };
    reader.readAsBinaryString(file);
    // Limpiar el valor del input para permitir cargar el mismo archivo de nuevo
    e.target.value = null; 
  };
  
  // --- NUEVO: Función que simula el clic en el input oculto ---
  const handleUploadClick = () => {
    fileInputRef.current.click();
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const validPieces = pieces
      .filter(p => Number(p.width) > 0 && Number(p.height) > 0)
      .map(p => ({ ...p, width: Number(p.width), height: Number(p.height) }));
    
    if (validPieces.length === 0) {
        alert("Por favor, añade al menos una pieza con dimensiones válidas.");
        return;
    }

    onSubmit({
      sheet: { width: Number(sheetWidth), height: Number(sheetHeight) },
      pieces: validPieces,
      kerf: Number(kerf),
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="control-group">
        <h3><FaRulerCombined /> Dimensiones de Lámina y Corte (mm)</h3>
        <div className="input-grid">
          <input type="number" value={sheetWidth} onChange={e => setSheetWidth(e.target.value)} placeholder="Ancho" required />
          <input type="number" value={sheetHeight} onChange={e => setSheetHeight(e.target.value)} placeholder="Alto" required />
          <input type="number" value={kerf} onChange={e => setKerf(e.target.value)} placeholder="Grosor (Kerf)" required />
        </div>
      </div>

      <div className="control-group">
        <h3><FaTh /> Piezas a Cortar (mm)</h3>
        {/* --- NUEVO: Input de archivo oculto --- */}
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={handleFileChange}
          style={{ display: 'none' }}
          accept=".xlsx, .xls"
        />
        <div className="button-group">
          <button type="button" className="button button-secondary" onClick={handleAddPiece}>
            <FaPlus /> Añadir Pieza
          </button>
          <button type="button" className="button button-success" onClick={handleUploadClick}>
            <FaFileExcel /> Cargar Excel
          </button>
        </div>

        {pieces.map((piece, index) => (
          <div key={index} className="piece-input-group">
            <input type="text" value={piece.id} onChange={e => handlePieceChange(index, 'id', e.target.value)} placeholder="ID Pieza" required/>
            <input type="number" value={piece.width} onChange={e => handlePieceChange(index, 'width', e.target.value)} placeholder="Ancho" required/>
            <input type="number" value={piece.height} onChange={e => handlePieceChange(index, 'height', e.target.value)} placeholder="Alto" required/>
            <button type="button" className="button button-danger" onClick={() => handleRemovePiece(index)} title="Eliminar pieza">
              <FaTrash />
            </button>
          </div>
        ))}
      </div>

      <button type="submit" className="button button-primary" disabled={isLoading}>
        <FaCogs /> {isLoading ? 'Optimizando...' : 'Optimizar Cortes'}
      </button>
    </form>
  );
}

export default InputForm;