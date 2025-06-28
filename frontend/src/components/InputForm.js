import React, { useState, useRef } from 'react';
import { FaRulerCombined, FaTh, FaPlus, FaTrashAlt, FaCogs, FaFileExcel, FaLayerGroup, FaWaveSquare, FaClock } from 'react-icons/fa';
import * as XLSX from 'xlsx';

const ToggleSwitch = ({ label, checked, onChange }) => (
  <div className="toggle-switch-container">
    <label className="toggle-switch">
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span className="slider round"></span>
    </label>
    <span>{label}</span>
  </div>
);

function InputForm({ onSubmit, isLoading }) {
  const [materialType, setMaterialType] = useState('sheet');
  const [sheetWidth, setSheetWidth] = useState(2440);
  const [sheetHeight, setSheetHeight] = useState(1220);
  const [rollWidth, setRollWidth] = useState(1370);
  const [kerf, setKerf] = useState(3);
  const [pieces, setPieces] = useState([{ id: 'P1', width: 600, height: 400, quantity: 1 }]);
  const [respectGrain, setRespectGrain] = useState(false);
  const fileInputRef = useRef(null);
  
  // --- NUEVOS ESTADOS PARA PARÁMETROS DE CORTE ---
  const [cuttingSpeed, setCuttingSpeed] = useState(50); // mm/s
  const [sheetThickness, setSheetThickness] = useState(18); // mm
  const [cutDepthPerPass, setCutDepthPerPass] = useState(6); // mm

  const handleAddPiece = () => {
    const newId = `P${pieces.length + 1}`;
    setPieces([...pieces, { id: newId, width: '', height: '', quantity: 1 }]);
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
    const file = e.target.files[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const workbook = XLSX.read(event.target.result, { type: 'binary' });
        const sheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[sheetName];
        const json = XLSX.utils.sheet_to_json(worksheet);
        const newPieces = json.map((row, index) => ({
          id: String(row.ID || row.id || `Pieza-${index + 1}`),
          width: Number(row.width || row.ancho || 0),
          height: Number(row.height || row.alto || 0),
          quantity: Number(row.Cant || row.cant || row.Cantidad || 1)
        })).filter(p => p.quantity > 0);
        setPieces(newPieces);
        alert(`${newPieces.length} tipos de pieza cargados.`);
      } catch (error) { console.error("Error al leer el archivo:", error); alert("Error al leer el archivo de Excel."); }
    };
    reader.readAsBinaryString(file); e.target.value = null; 
  };
  
  const handleUploadClick = () => { fileInputRef.current.click(); };

  const handleSubmit = (e) => {
    e.preventDefault();
    const validPieces = pieces
      .filter(p => Number(p.width) > 0 && Number(p.height) > 0 && Number(p.quantity) > 0)
      .map(p => ({ id: String(p.id), width: Number(p.width), height: Number(p.height), quantity: parseInt(p.quantity, 10) }));
    
    if (validPieces.length === 0) { alert("Añade al menos una pieza válida."); return; }
    
    onSubmit({
      material_type: materialType,
      sheet: materialType === 'sheet' ? { width: Number(sheetWidth), height: Number(sheetHeight) } : { width: Number(rollWidth), height: -1 },
      pieces: validPieces,
      kerf: Number(kerf),
      respect_grain: respectGrain,
      // --- ENVIAR NUEVOS PARÁMETROS ---
      cutting_speed_mms: Number(cuttingSpeed),
      sheet_thickness_mm: Number(sheetThickness),
      cut_depth_per_pass_mm: Number(cutDepthPerPass),
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="control-group">
        <h3><FaLayerGroup /> Tipo de Material</h3>
        <div className="material-type-selector">
          <label className={materialType === 'sheet' ? 'active' : ''}><input type="radio" value="sheet" checked={materialType === 'sheet'} onChange={() => setMaterialType('sheet')} />Lámina</label>
          <label className={materialType === 'roll' ? 'active' : ''}><input type="radio" value="roll" checked={materialType === 'roll'} onChange={() => setMaterialType('roll')} />Rollo</label>
        </div>
      </div>
      <div className="control-group">
        <h3><FaRulerCombined /> Dimensiones y Configuración</h3>
        {materialType === 'sheet' ? (
          <div className="input-grid">
            <input type="number" value={sheetWidth} onChange={e => setSheetWidth(e.target.value)} placeholder="Ancho" required />
            <input type="number" value={sheetHeight} onChange={e => setSheetHeight(e.target.value)} placeholder="Alto" required />
          </div>
        ) : (
          <div className="input-grid-single"><input type="number" value={rollWidth} onChange={e => setRollWidth(e.target.value)} placeholder="Ancho del Rollo" required /></div>
        )}
        <div className="input-grid-single" style={{marginTop: '1rem', marginBottom: '1.5rem'}}>
            <label className="input-label">Grosor de Cuchilla / Fresa (Kerf en mm)</label>
            <input type="number" value={kerf} onChange={e => setKerf(e.target.value)} required />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.5rem' }}>
          <FaWaveSquare size="1.2em" color="var(--text-muted)"/>
          <ToggleSwitch label="Respetar Veta (no rotar)" checked={respectGrain} onChange={(e) => setRespectGrain(e.target.checked)} />
        </div>
      </div>
      {/* --- NUEVO GRUPO PARA PARÁMETROS DE LA MÁQUINA --- */}
      <div className="control-group">
        <h3><FaClock /> Parámetros de la Máquina</h3>
        <div className="input-grid-single">
            <label className="input-label">Velocidad de Corte (mm/s)</label>
            <input type="number" value={cuttingSpeed} onChange={e => setCuttingSpeed(e.target.value)} required />
        </div>
        {materialType === 'sheet' && (
            <div className="input-grid" style={{marginTop: '1rem'}}>
                <div>
                    <label className="input-label">Grosor de Lámina (mm)</label>
                    <input type="number" value={sheetThickness} onChange={e => setSheetThickness(e.target.value)} required />
                </div>
                <div>
                    <label className="input-label">Corte por Pasada (mm)</label>
                    <input type="number" value={cutDepthPerPass} onChange={e => setCutDepthPerPass(e.target.value)} required />
                </div>
            </div>
        )}
      </div>
      <div className="control-group">
        <h3><FaTh /> Piezas a Cortar (mm)</h3>
        <input type="file" ref={fileInputRef} onChange={handleFileChange} style={{ display: 'none' }} accept=".xlsx, .xls, .csv" />
        <div className="button-group">
          <button type="button" className="button button-secondary" onClick={handleAddPiece}><FaPlus /> Añadir Fila</button>
          <button type="button" className="button button-success" onClick={handleUploadClick}><FaFileExcel /> Cargar Excel</button>
        </div>
        {pieces.map((piece, index) => (
          <div key={index} className="piece-input-group">
            <input type="text" value={piece.id} onChange={e => handlePieceChange(index, 'id', e.target.value)} placeholder="ID" required/>
            <input type="number" value={piece.width} onChange={e => handlePieceChange(index, 'width', e.target.value)} placeholder="Ancho" required/>
            <input type="number" value={piece.height} onChange={e => handlePieceChange(index, 'height', e.target.value)} placeholder="Alto" required/>
            <input type="number" value={piece.quantity} min="1" onChange={e => handlePieceChange(index, 'quantity', e.target.value)} placeholder="Cant." required/>
            <button type="button" className="button button-danger" onClick={() => handleRemovePiece(index)} title="Eliminar"><FaTrashAlt /></button>
          </div>
        ))}
      </div>
      <button type="submit" className="button button-primary" disabled={isLoading}><FaCogs /> {isLoading ? 'Optimizando...' : 'Optimizar Cortes'}</button>
    </form>
  );
}

export default InputForm;