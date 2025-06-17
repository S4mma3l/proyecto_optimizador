import React, { useRef, useEffect } from 'react';
import { FaCheckCircle, FaExclamationTriangle, FaTh, FaBan, FaTape } from 'react-icons/fa';

// --- Funciones Auxiliares ---
const generatePastelColor = () => {
  const h = Math.floor(Math.random() * 360);
  return `hsl(${h}, 75%, 85%)`;
};

const getTextColorForBackground = () => 'black';

// --- Componente para una Sola Lámina/Rollo ---
const SingleSheetLayout = ({ sheetData, pieceColors }) => {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const { width: sheetWidth, height: sheetHeight } = sheetData.sheet_dimensions;
        
        const devicePixelRatio = window.devicePixelRatio || 1;
        canvas.width = sheetWidth * devicePixelRatio;
        canvas.height = sheetHeight * devicePixelRatio;
        
        const aspectRatio = sheetWidth / sheetHeight;
        canvas.style.width = '100%';
        canvas.style.height = 'auto';
        canvas.style.aspectRatio = aspectRatio;

        ctx.scale(devicePixelRatio, devicePixelRatio);

        ctx.fillStyle = '#fdfdfd';
        ctx.fillRect(0, 0, sheetWidth, sheetHeight);
        ctx.strokeStyle = '#e0e0e0';
        ctx.lineWidth = 2;
        ctx.strokeRect(0, 0, sheetWidth, sheetHeight);

        sheetData.placed_pieces.forEach(piece => {
            ctx.fillStyle = pieceColors.current.get(piece.id) || 'gray';
            ctx.strokeStyle = '#333';
            ctx.lineWidth = 1;
            
            ctx.fillRect(piece.x, piece.y, piece.width, piece.height);
            ctx.strokeRect(piece.x, piece.y, piece.width, piece.height);

            ctx.fillStyle = getTextColorForBackground();
            const fontSize = Math.max(10, Math.min(piece.width, piece.height) / 5);
            ctx.font = `bold ${fontSize}px Arial`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            
            const label = piece.id;
            const dimensions = `${piece.width}x${piece.height}`;
            
            ctx.fillText(label, piece.x + piece.width / 2, piece.y + piece.height / 2 - fontSize / 2);
            ctx.fillText(dimensions, piece.x + piece.width / 2, piece.y + piece.height / 2 + fontSize / 2);
        });
    }, [sheetData, pieceColors]);

    return (
        <div className="single-sheet-container">
            <h4>
                {sheetData.sheet_index === 1 && sheetData.metrics.consumed_length_mm ? 'Resultado del Rollo' : `Lámina #${sheetData.sheet_index}`}
                <span className="sheet-metrics">
                    ({sheetData.metrics.piece_count} piezas | 
                    {sheetData.metrics.efficiency_percentage ? ` Eficiencia: ${sheetData.metrics.efficiency_percentage}%` : ''})
                </span>
            </h4>
            <div className="canvas-wrapper">
                <canvas ref={canvasRef} />
            </div>
        </div>
    );
};

// --- Componente Principal del Layout ---
function CuttingLayout({ result, isLoading, error, layoutRef }) {
  const pieceColors = useRef(new Map());

  useEffect(() => {
    if (result && result.sheets) {
        pieceColors.current.clear();
        result.sheets.forEach(sheet => {
            sheet.placed_pieces.forEach(piece => {
                if (!pieceColors.current.has(piece.id)) {
                    pieceColors.current.set(piece.id, generatePastelColor());
                }
            });
        });
    }
  }, [result]);

  return (
    <div ref={layoutRef}>
      {isLoading && <div className="loader-container"><div className="loader"></div><p>Optimizando...</p></div>}
      {error && <p className="error-message">{error}</p>}
      {!isLoading && !error && !result && <p className="placeholder-text">Los resultados aparecerán aquí.</p>}
      
      {result && result.global_metrics && (
        <div className="results-summary">
          <h3>Resumen Global</h3>
          <div className="metrics-grid">
            {/* MÉTRICAS CONDICIONALES */}
            {result.global_metrics.material_type === 'sheet' ? (
              <MetricCard icon={<FaCheckCircle />} title="Láminas Usadas" value={result.global_metrics.total_sheets_used} />
            ) : (
              // --- ¡AQUÍ ESTÁ LA CORRECCIÓN! ---
              // Usamos optional chaining (?.) y el operador Nullish Coalescing (??)
              // para evitar el error si el valor es undefined.
              <MetricCard 
                icon={<FaTape />} 
                title="Largo Consumido" 
                value={`${(result.sheets?.[0]?.metrics?.consumed_length_mm ?? 0).toFixed(0)} mm`} 
              />
            )}

            <MetricCard icon={<FaTh />} title="Piezas Colocadas" value={`${result.global_metrics.total_placed_pieces} / ${result.global_metrics.total_pieces}`} className={result.global_metrics.total_placed_pieces < result.global_metrics.total_pieces ? 'danger' : 'success'} />
            
            {result.impossible_to_place_ids && result.impossible_to_place_ids.length > 0 && 
              <MetricCard icon={<FaBan />} title="Piezas Imposibles" value={result.impossible_to_place_ids.length} className="danger" />}
            
            {result.unplaced_piece_ids && result.unplaced_piece_ids.length > 0 && 
              <MetricCard icon={<FaExclamationTriangle />} title="Piezas Sin Espacio" value={result.unplaced_piece_ids.length} className="danger" />}
          </div>

          {result.impossible_to_place_ids && result.impossible_to_place_ids.length > 0 && 
            <p className='warning-message'>IDs imposibles: {result.impossible_to_place_ids.join(', ')}</p>}
        </div>
      )}

      {result && result.sheets && result.sheets.map(sheetData => (
          <SingleSheetLayout 
            key={sheetData.sheet_index} 
            sheetData={sheetData}
            pieceColors={pieceColors}
          />
      ))}
    </div>
  );
}

// --- Componente de Tarjeta de Métrica ---
const MetricCard = ({ icon, title, value, className = '' }) => (
  <div className="metric-card">
    <div className="metric-card-title">{icon} {title}</div>
    <div className={`metric-card-value ${className}`}>{value}</div>
  </div>
);

export default CuttingLayout;