import React, { useRef, useEffect } from 'react';
import { FaCheckCircle, FaExclamationTriangle, FaTh, FaBan, FaTape, FaTrashAlt } from 'react-icons/fa';

const generatePastelColor = () => `hsl(${Math.floor(Math.random() * 360)}, 75%, 85%)`;
const getTextColorForBackground = () => 'black';

const SingleSheetLayout = ({ sheetData, pieceColors }) => {
    const canvasRef = useRef(null);
    useEffect(() => {
        const canvas = canvasRef.current; if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const { width: sheetWidth, height: sheetHeight } = sheetData.sheet_dimensions;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = sheetWidth * dpr; canvas.height = sheetHeight * dpr;
        canvas.style.aspectRatio = `${sheetWidth} / ${sheetHeight}`;
        ctx.scale(dpr, dpr);
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, sheetWidth, sheetHeight);
        ctx.strokeStyle = '#e5e7eb'; ctx.lineWidth = 2; ctx.strokeRect(0, 0, sheetWidth, sheetHeight);
        sheetData.placed_pieces.forEach(p => {
            const baseId = p.id.split('-')[0];
            ctx.fillStyle = pieceColors.current.get(baseId) || 'gray'; ctx.strokeStyle = '#333'; ctx.lineWidth = 1;
            ctx.fillRect(p.x, p.y, p.width, p.height); ctx.strokeRect(p.x, p.y, p.width, p.height);
            ctx.fillStyle = getTextColorForBackground();
            const fontSize = Math.max(10, Math.min(p.width, p.height) / 5);
            ctx.font = `bold ${fontSize}px Arial`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            const label = baseId; const dims = `${p.width}x${p.height}`;
            ctx.fillText(label, p.x + p.width / 2, p.y + p.height / 2 - fontSize/2);
            ctx.fillText(dims, p.x + p.width / 2, p.y + p.height / 2 + fontSize/2);
        });
    }, [sheetData, pieceColors]);

    return (
        <div className="single-sheet-container">
            <h4>
                <span>
                    {sheetData.metrics.consumed_length_mm !== undefined ? 'Resultado del Rollo' : `Lámina #${sheetData.sheet_index}`}
                </span>
                <span className="sheet-metrics">
                    ({sheetData.metrics.piece_count} piezas)
                </span>
            </h4>
            <div className="canvas-wrapper"><canvas ref={canvasRef} /></div>
        </div>
    );
};

function CuttingLayout({ result, isLoading, error, layoutRef }) {
  const pieceColors = useRef(new Map());
  useEffect(() => {
    if (result && result.sheets) {
        pieceColors.current.clear();
        result.sheets.forEach(s => s.placed_pieces.forEach(p => {
            const baseId = p.id.split('-')[0];
            if (!pieceColors.current.has(baseId)) {
                pieceColors.current.set(baseId, generatePastelColor());
            }
        }));
    }
  }, [result]);

  const wastePercentage = result?.global_metrics?.waste_percentage;

  return (
    <div ref={layoutRef}>
      {isLoading && <div className="loader-container"><div className="loader"></div><p>Optimizando...</p></div>}
      {error && <p className="error-message">{error}</p>}
      {!isLoading && !error && !result && <p className="placeholder-text">Los resultados aparecerán aquí.</p>}
      
      {result && result.global_metrics && (
        <div className="results-summary">
          <h3>Resumen Global</h3>
          <div className="metrics-grid">
            {result.global_metrics.material_type === 'sheet' ? (
              <MetricCard icon={<FaCheckCircle />} title="Láminas Usadas" value={result.global_metrics.total_sheets_used} />
            ) : (
              <MetricCard icon={<FaTape />} title="Largo Consumido" value={`${(result.sheets?.[0]?.sheet_dimensions?.height ?? 0).toFixed(0)} mm`} />
            )}
            <MetricCard icon={<FaTh />} title="Piezas Colocadas" value={`${result.global_metrics.total_placed_pieces} / ${result.global_metrics.total_pieces}`} className={result.global_metrics.total_placed_pieces < result.global_metrics.total_pieces ? 'danger' : 'success'} />
            {wastePercentage !== undefined && (
              <MetricCard icon={<FaTrashAlt />} title="Desperdicio" value={`${wastePercentage}%`} className="warning" />
            )}
            {result.impossible_to_place_ids?.length > 0 && <MetricCard icon={<FaBan />} title="Piezas Imposibles" value={result.impossible_to_place_ids.length} className="danger" />}
            {result.unplaced_piece_ids?.length > 0 && <MetricCard icon={<FaExclamationTriangle />} title="Piezas Sin Espacio" value={result.unplaced_piece_ids.length} className="danger" />}
          </div>
          {result.impossible_to_place_ids?.length > 0 && <p className='warning-message'>IDs imposibles: {result.impossible_to_place_ids.join(', ')}</p>}
        </div>
      )}
      {result?.sheets?.map(sheetData => <SingleSheetLayout key={sheetData.sheet_index} sheetData={sheetData} pieceColors={pieceColors}/>)}
    </div>
  );
}

const MetricCard = ({ icon, title, value, className = '' }) => (
  <div className="metric-card"><div className="metric-card-title">{icon} {title}</div><div className={`metric-card-value ${className}`}>{value}</div></div>
);

export default CuttingLayout;