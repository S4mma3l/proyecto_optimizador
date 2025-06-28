import React, { useRef, useEffect } from 'react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { FaCheckCircle, FaExclamationTriangle, FaTh, FaBan, FaTape, FaTrashAlt, FaFilePdf, FaBoxes, FaClock } from 'react-icons/fa';

// --- ¡FUNCIONES AUXILIARES RESTAURADAS AQUÍ! ---
const generatePastelColor = () => `hsl(${Math.floor(Math.random() * 360)}, 75%, 85%)`;
const getTextColorForBackground = () => 'black'; // Para pasteles claros, el negro siempre es legible.

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
            if (p.width > 30 && p.height > 20) {
              ctx.fillStyle = getTextColorForBackground(); // Ahora esta función existe
              const fontSize = Math.max(10, Math.min(p.width, p.height) / 5);
              ctx.font = `bold ${fontSize}px Arial`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
              const label = baseId; const dims = `${p.width}x${p.height}`;
              ctx.fillText(label, p.x + p.width / 2, p.y + p.height / 2 - fontSize/2);
              ctx.fillText(dims, p.x + p.width / 2, p.y + p.height / 2 + fontSize/2);
            }
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

// --- NUEVA FUNCIÓN HELPER PARA FORMATEAR EL TIEMPO ---
const formatTime = (totalSeconds) => {
  if (totalSeconds < 0 || !totalSeconds) return "0s";
  totalSeconds = Math.round(totalSeconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  let timeString = "";
  if (hours > 0) timeString += `${hours}h `;
  if (minutes > 0) timeString += `${minutes}m `;
  if (seconds > 0 || timeString === "") timeString += `${seconds}s`;
  return timeString.trim();
};

function CuttingLayout({ result, isLoading, error }) {
  const pieceColors = useRef(new Map());
  const resultsContainerRef = useRef(null);

  useEffect(() => {
    if (result && result.sheets) {
        pieceColors.current.clear();
        result.sheets.forEach(s => s.placed_pieces.forEach(p => {
            const baseId = p.id.split('-')[0];
            if (!pieceColors.current.has(baseId)) {
                pieceColors.current.set(baseId, generatePastelColor()); // Ahora esta función existe
            }
        }));
    }
  }, [result]);

  const handleDownloadPdf = async () => {
    const container = resultsContainerRef.current;
    if (!container || !result) return;
    const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4', compress: true });
    const pdfWidth = pdf.internal.pageSize.getWidth();
    const pdfHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    pdf.setFontSize(18); pdf.text('Reporte de Optimización de Corte', pdfWidth / 2, margin + 5, { align: 'center' });
    let yPos = margin + 20;

    if (result.global_metrics.material_type === 'roll') {
        const rollElement = container.querySelector('.single-sheet-container');
        if (!rollElement) return;
        const canvas = await html2canvas(rollElement, { scale: 2, useCORS: true, backgroundColor: '#ffffff', windowWidth: rollElement.scrollWidth, windowHeight: rollElement.scrollHeight });
        const imgData = canvas.toDataURL('image/png');
        const imgWidth = pdfWidth - margin * 2;
        const imgHeight = (canvas.height * imgWidth) / canvas.width;
        let heightLeft = imgHeight, position = 0;
        pdf.addImage(imgData, 'PNG', margin, yPos, imgWidth, imgHeight);
        heightLeft -= (pdfHeight - yPos);
        while (heightLeft > 0) {
            position -= (pdfHeight - margin * 2);
            pdf.addPage();
            pdf.addImage(imgData, 'PNG', margin, position, imgWidth, imgHeight);
            heightLeft -= pdfHeight;
        }
    } else {
        const sheetElements = Array.from(container.querySelectorAll('.single-sheet-container'));
        if (sheetElements.length === 0) return;
        for (const sheet of sheetElements) {
            const canvas = await html2canvas(sheet, { scale: 2, useCORS: true, backgroundColor: '#ffffff' });
            const imgData = canvas.toDataURL('image/png');
            const imgWidth = pdfWidth - margin * 2;
            const imgHeight = (canvas.height * imgWidth) / canvas.width;
            if (yPos + imgHeight > pdfHeight - margin) {
                pdf.addPage();
                yPos = margin;
            }
            pdf.addImage(imgData, 'PNG', margin, yPos, imgWidth, imgHeight);
            yPos += imgHeight + 10;
        }
    }
    pdf.save('reporte-de-optimizacion.pdf');
  };

  const { global_metrics: metrics } = result || {};

  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', height: '100%' }}>
      {isLoading && (
        <div className="glass-pane-overlay">
          <div className="loading-dots-container">
            <div className="loading-dot"></div><div className="loading-dot"></div><div className="loading-dot"></div>
          </div>
          <span>Optimizando...</span>
        </div>
      )}
      <div className="results-area">
        {error && <p className="error-message">{error}</p>}
        {!isLoading && !error && !result && <p className="placeholder-text">Los resultados aparecerán aquí.</p>}
        {metrics && (
          <div className="results-summary">
            <h3>Resumen Global</h3>
            <div className="metrics-grid">
              {metrics.material_type === 'sheet' ? (<MetricCard icon={<FaCheckCircle />} title="Láminas Usadas" value={metrics.total_sheets_used} />) : (<MetricCard icon={<FaTape />} title="Largo Consumido" value={`${(result.sheets?.[0]?.sheet_dimensions?.height ?? 0).toFixed(0)} mm`} />)}
              {metrics.total_material_area_sqm !== undefined && (<MetricCard icon={<FaBoxes />} title="Material Usado" value={`${metrics.total_material_area_sqm} m²`} />)}
              <MetricCard icon={<FaTh />} title="Piezas Colocadas" value={`${metrics.total_placed_pieces} / ${metrics.total_pieces}`} className={metrics.total_placed_pieces < metrics.total_pieces ? 'danger' : 'success'} />
              {metrics.waste_percentage !== undefined && (<MetricCard icon={<FaTrashAlt />} title="Desperdicio" value={`${metrics.waste_percentage}%`} className="warning" />)}
              {metrics.estimated_time_seconds !== undefined && ( <MetricCard icon={<FaClock />} title="Tiempo de Corte" value={formatTime(metrics.estimated_time_seconds)} /> )}
              {result.impossible_to_place_ids?.length > 0 && <MetricCard icon={<FaBan />} title="Piezas Imposibles" value={result.impossible_to_place_ids.length} className="danger" />}
              {result.unplaced_piece_ids?.length > 0 && <MetricCard icon={<FaExclamationTriangle />} title="Piezas Sin Espacio" value={result.unplaced_piece_ids.length} className="danger" />}
            </div>
            {result.impossible_to_place_ids?.length > 0 && <p className='warning-message'>IDs imposibles: {result.impossible_to_place_ids.join(', ')}</p>}
          </div>
        )}
        {result && result.sheets && result.sheets.length > 0 && (
            <button onClick={handleDownloadPdf} className="button button-primary" style={{ marginBottom: '1.5rem', width: 'auto', alignSelf: 'flex-start' }}>
              <FaFilePdf /> Descargar Reporte PDF
            </button>
        )}
        <div className="sheets-list-container" ref={resultsContainerRef}>
          {result?.sheets?.map(sheetData => <SingleSheetLayout key={sheetData.sheet_index} sheetData={sheetData} pieceColors={pieceColors}/>)}
        </div>
      </div>
    </div>
  );
}

const MetricCard = ({ icon, title, value, className = '' }) => (
  <div className="metric-card"><div className="metric-card-title">{icon} {title}</div><div className={`metric-card-value ${className}`}>{value}</div></div>
);

export default CuttingLayout;