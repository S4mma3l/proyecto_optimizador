import React, { useState, useRef } from 'react';
import InputForm from './components/InputForm';
import CuttingLayout from './components/CuttingLayout';
import './App.css';
import { VscTools } from 'react-icons/vsc';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { FaFilePdf } from 'react-icons/fa';

function App() {
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const layoutRef = useRef(null); // Ref para el contenedor de todos los layouts

  const handleOptimize = async (requestData) => {
    setIsLoading(true);
    setError('');
    setResult(null);

    try {
      const apiUrl = `${process.env.REACT_APP_API_URL}/api/optimize`;
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(`Error en la API: ${errData.detail || 'Ocurrió un error desconocido'}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };
  
  // --- FUNCIÓN DE EXPORTACIÓN A PDF CORREGIDA ---
  const handleDownloadPdf = async () => {
    const container = layoutRef.current;
    if (!container) {
      alert("No hay resultados para exportar.");
      return;
    }

    const sheetElements = container.querySelectorAll('.single-sheet-container');
    if (sheetElements.length === 0) {
      alert("No hay láminas para exportar en el PDF.");
      return;
    }

    // 1. Marcar la función como 'async'
    const pdf = new jsPDF('p', 'mm', 'a4'); // 'p' for portrait
    const pdfWidth = pdf.internal.pageSize.getWidth();
    const pdfHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    
    // Añadir un título al PDF
    pdf.setFontSize(18);
    pdf.text('Reporte de Optimización de Corte', pdfWidth / 2, margin + 5, { align: 'center' });
    
    let yPos = margin + 20; // Posición Y inicial para la primera imagen

    // 2. Usar un bucle 'for...of' en lugar de 'forEach'
    for (const sheet of sheetElements) {
      // 3. Usar 'await' para esperar a que html2canvas termine
      const canvas = await html2canvas(sheet, { 
          scale: 2, // Mejor resolución
          useCORS: true, 
          backgroundColor: '#ffffff' // Fondo blanco para evitar transparencias
      });

      const imgData = canvas.toDataURL('image/png');
      const imgWidth = pdfWidth - margin * 2;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;

      // Comprobar si la imagen cabe en la página actual
      if (yPos + imgHeight > pdfHeight - margin) {
        pdf.addPage(); // Añadir nueva página si no cabe
        yPos = margin; // Resetear la posición Y en la nueva página
      }

      pdf.addImage(imgData, 'PNG', margin, yPos, imgWidth, imgHeight);
      yPos += imgHeight + 10; // Incrementar la posición Y para la siguiente imagen, con un espacio
    }

    // 4. Guardar el PDF DESPUÉS de que el bucle haya terminado completamente
    pdf.save('reporte-de-corte.pdf');
  };

  return (
    <div className="App">
      <header className="App-header">
        <VscTools size="1.5em" />
        <h1>Optimizador de Corte</h1>
      </header>
      <main>
        <div className="controls-panel">
          <InputForm onSubmit={handleOptimize} isLoading={isLoading} />
        </div>
        <div className="layout-container">
          {/* Pasamos el ref al componente hijo para que pueda asignarlo */}
          <CuttingLayout result={result} isLoading={isLoading} error={error} layoutRef={layoutRef} />
          
          {/* El botón de descarga se queda aquí, en el componente padre */}
          {result && result.sheets && result.sheets.length > 0 && (
            <button onClick={handleDownloadPdf} className="button button-primary" style={{ marginTop: '1rem' }}>
              <FaFilePdf /> Descargar Reporte PDF
            </button>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;