import React, { useRef, useEffect } from 'react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { FaCheckCircle, FaExclamationTriangle, FaTh, FaBan, FaTape, FaTrashAlt, FaFilePdf, FaBoxes } from 'react-icons/fa';

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
            if (p.width > 30 && p.height > 20) {
              ctx.fillStyle = getTextColorForBackground();
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

function CuttingLayout({ result, isLoading, error }) {
  const pieceColors = useRef(new Map());
  const resultsToPrintRef = useRef(null); // Ref al área que queremos imprimir

  useEffect(() => {
    if (result && result.sheets) {
        pieceColors.current.clear();
        result.sheets.forEach(s => s.placed_pieces.forEach(p => {
            const baseId = p.id.split('-')[0];
            if (!pieceColors.current.has(baseId)) pieceColors.current.set(baseId, generatePastelColor());
        }));
    }
  }, [result]);

  // --- FUNCIÓN DE DESCARGA DE PDF CORREGIDA Y ROBUSTA ---
  const handleDownloadPdf = async () => {
    const reportElement = resultsToPrintRef.current;
    if (!reportElement) return;

    // Guardar los estilos originales
    const originalHeight = reportElement.style.height;
    const originalOverflow = reportElement.style.overflow;

    // 1. Modificar estilos para hacer todo el contenido visible para html2canvas
    reportElement.style.height = 'auto';
    reportElement.style.overflow = 'visible';
    
    // Pequeña demora para asegurar que el DOM se actualice antes de la captura
    await new Promise(resolve => setTimeout(resolve, 50));

    try {
        const canvas = await html2canvas(reportElement, {
            scale: 2, // Mejor resolución
            useCORS: true,
            backgroundColor: '#ffffff',
            // Opciones para asegurar que capture el contenido completo
            windowWidth: reportElement.scrollWidth,
            windowHeight: reportElement.scrollHeight
        });
        
        // 2. Restaurar los estilos originales inmediatamente después de la captura
        reportElement.style.height = originalHeight;
        reportElement.style.overflow = originalOverflow;

        const imgData = canvas.toDataURL('image/png');
        const pdf = new jsPDF({
            orientation: 'p',
            unit: 'mm',
            format: 'a4',
            compress: true
        });

        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pdfHeight = pdf.internal.pageSize.getHeight();
        const canvasWidth = canvas.width;
        const canvasHeight = canvas.height;
        const ratio = canvasWidth / canvasHeight;

        let imgHeight = pdfWidth / ratio;
        let heightLeft = imgHeight;
        let position = 0;

        // Añadir la primera página
        pdf.addImage(imgData, 'PNG', 0, position, pdfWidth, imgHeight);
        heightLeft -= pdfHeight;

        // Añadir más páginas si es necesario
        while (heightLeft > 0) {
            position = heightLeft - imgHeight;
            pdf.addPage();
            pdf.addImage(imgData, 'PNG', 0, position, pdfWidth, imgHeight);
            heightLeft -= pdfHeight;
        }

        pdf.save('reporte-de-optimizacion.pdf');
    } catch (err) {
        console.error("Error al generar el PDF:", err);
        // Restaurar estilos también si hay un error
        reportElement.style.height = originalHeight;
        reportElement.style.overflow = originalOverflow;
    }
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
      
      {/* El ref se asigna al área que contiene todo lo que se va a imprimir */}
      <div className="results-area" ref={resultsToPrintRef}>
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
        
        {result?.sheets?.map(sheetData => <SingleSheetLayout key={sheetData.sheet_index} sheetData={sheetData} pieceColors={pieceColors}/>)}
      </div>
    </div>
  );
}

const MetricCard = ({ icon, title, value, className = '' }) => (
  <div className="metric-card"><div className="metric-card-title">{icon} {title}</div><div className={`metric-card-value ${className}`}>{value}</div></div>
);

export default CuttingLayout;