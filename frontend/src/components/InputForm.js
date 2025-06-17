import React, { useState, useRef } from 'react';
import { FaRulerCombined, FaTh, FaPlus, FaTrash, FaCogs, FaFileExcel, FaLayerGroup } from 'react-icons/fa';
import * as XLSX from 'xlsx';

function InputForm({ onSubmit, isLoading }) {
  // Estado para el tipo de material
  const [materialType, setMaterialType] = useState('sheet'); // 'sheet' o 'roll'

  // Estados para las dimensiones
  const [sheetWidth, setSheetWidth] = useState(2440);
  const [sheetHeight, setSheetHeight] = useState(1220);
  const [rollWidth, setRollWidth] = useState(1220);
  const [kerf, setKerf] = useState(3);
  
  const [pieces, setPieces] = useState([{ id: 'P1', width: 600, height: 400 }]);
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

        const newPieces = [];
        json.forEach((row, rowIndex) => {
          const id = String(row.ID || row.id || row.Id || `Pieza-${rowIndex + 1}`);
          const width = row.width || row.ancho || row.ANCHO;
          const height = row.height || row.alto || row.ALTO;
          const quantity = row.Cant || row.cant || row.Cantidad || row.cantidad || 1;

          if (width && height) {
            for (let i = 0; i < quantity; i++) {
              const uniqueId = quantity > 1 ? `${id}-${i + 1}` : id;
              newPieces.push({ id: uniqueId, width: Number(width), height: Number(height) });
            }
          }
        });
        setPieces(newPieces);
        alert(`${newPieces.length} piezas cargadas exitosamente.`);
      } catch (error) {
        console.error("Error al procesar el archivo de Excel", error);
        alert("Ocurrió un error al leer el archivo.");
      }
    };
    reader.readAsBinaryString(file);
    e.target.value = null; 
  };
  
  const handleUploadClick = () => {
    fileInputRef.current.click();
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const validPieces = pieces
      .filter(p => Number(p.width) > 0 && Number(p.height) > 0)
      .map(p => ({ ...p, id: String(p.id), width: Number(p.width), height: Number(p.height) }));
    
    if (validPieces.length === 0) {
      alert("Por favor, añade al menos una pieza válida.");
      return;
    }

    // Construir los datos de la solicitud dinámicamente
    const requestData = {
      material_type: materialType,
      sheet: materialType === 'sheet' 
        ? { width: Number(sheetWidth), height: Number(sheetHeight) }
        : { width: Number(rollWidth), height: -1 }, // Para rollos, la altura es simbólica
      pieces: validPieces,
      kerf: Number(kerf),
    };

    onSubmit(requestData);
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="control-group">
        <h3><FaLayerGroup /> Tipo de Material</h3>
        <div className="material-type-selector">
          <label className={materialType === 'sheet' ? 'active' : ''}>
            <input type="radio" name="materialType" value="sheet" checked={materialType === 'sheet'} onChange={() => setMaterialType('sheet')} />
            Lámina
          </label>
          <label className={materialType === 'roll' ? 'active' : ''}>
            <input type="radio" name="materialType" value="roll" checked={materialType === 'roll'} onChange={() => setMaterialType('roll')} />
            Rollo
          </label>
        </div>
      </div>

      <div className="control-group">
        <h3><FaRulerCombined /> Dimensiones del Material (mm)</h3>
        {materialType === 'sheet' ? (
          <div className="input-grid">
            <input type="number" value={sheetWidth} onChange={e => setSheetWidth(e.target.value)} placeholder="Ancho Lámina" required />
            <input type="number" value={sheetHeight} onChange={e => setSheetHeight(e.target.value)} placeholder="Alto Lámina" required />
          </div>
        ) : (
          <div className="input-grid-single">
            <input type="number" value={rollWidth} onChange={e => setRollWidth(e.target.value)} placeholder="Ancho del Rollo" required />
          </div>
        )}
        <div className="input-grid-single" style={{marginTop: '1rem'}}>
          <input type="number" value={kerf} onChange={e => setKerf(e.target.value)} placeholder="Grosor Corte (Kerf)" required />
        </div>
      </div>

      <div className="control-group">
        <h3><FaTh /> Piezas a Cortar (mm)</h3>
        <input type="file" ref={fileInputRef} onChange={handleFileChange} style={{ display: 'none' }} accept=".xlsx, .xls" />
        <div className="button-group">
          <button type="button" className="button button-secondary" onClick={handleAddPiece}><FaPlus /> Añadir Pieza</button>
          <button type="button" className="button button-success" onClick={handleUploadClick}><FaFileExcel /> Cargar Excel</button>
        </div>
        {pieces.map((piece, index) => (
          <div key={index} className="piece-input-group">
            <input type="text" value={piece.id} onChange={e => handlePieceChange(index, 'id', e.target.value)} required/>
            <input type="number" value={piece.width} onChange={e => handlePieceChange(index, 'width', e.target.value)} required/>
            <input type="number" value={piece.height} onChange={e => handlePieceChange(index, 'height', e.target.value)} required/>
            <button type="button" className="button button-danger" onClick={() => handleRemovePiece(index)} title="Eliminar pieza"><FaTrash /></button>
          </div>
        ))}
      </div>
      <button type="submit" className="button button-primary" disabled={isLoading}>{isLoading ? 'Optimizando...' : 'Optimizar Cortes'}</button>
    </form>
  );
}

export default InputForm;