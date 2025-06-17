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
  const layoutRef = useRef(null);

  // --- FUNCIÓN DE OPTIMIZACIÓN CON MANEJO DE ESTADO MEJORADO ---
  const handleOptimize = async (requestData) => {
    // 1. Limpiar el estado anterior INMEDIATAMENTE
    // Esto asegura que cualquier "fantasma" de un error pasado desaparezca.
    console.log("Limpiando resultados anteriores...");
    setIsLoading(true);
    setError('');
    setResult(null);

    try {
      // URL de tu API de producción.
      const apiUrl = 'https://proyectooptimizador-production.up.railway.app/api/optimize'; 

      console.log("Enviando solicitud a:", apiUrl);
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData),
      });

      console.log("Respuesta recibida. Status:", response.status);

      // 2. Manejar respuestas no exitosas de forma explícita
      if (!response.ok) {
        // Intenta leer el cuerpo del error como JSON, si falla, lee como texto.
        const errorBody = await response.json().catch(() => response.text());
        const errorMsg = typeof errorBody === 'object' ? JSON.stringify(errorBody.detail) : errorBody;
        console.error(`Respuesta de error de la API (${response.status}):`, errorMsg);
        throw new Error(`Error ${response.status}: ${errorMsg}`);
      }

      // 3. Procesar la respuesta exitosa
      const data = await response.json();
      console.log("Solicitud exitosa. Actualizando estado con nuevos datos:", data);
      setResult(data);

    } catch (err) {
      // 4. Capturar errores de red o fallos en el bloque try
      console.error("Error durante la solicitud fetch:", err);
      // Muestra un mensaje de error claro al usuario
      setError(`Error al conectar con la API. Por favor, revisa la consola.`);
    } finally {
      // 5. Asegurarse de que el estado de carga se desactive siempre
      setIsLoading(false);
    }
  };
  
  // --- FUNCIÓN DE EXPORTACIÓN A PDF (sin cambios) ---
  const handleDownloadPdf = async () => {
    const container = layoutRef.current;
    if (!container) return;

    const sheetElements = container.querySelectorAll('.single-sheet-container');
    if (sheetElements.length === 0) return;

    const pdf = new jsPDF('p', 'mm', 'a4');
    const pdfWidth = pdf.internal.pageSize.getWidth();
    const pdfHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    
    pdf.setFontSize(18);
    pdf.text('Reporte de Optimización de Corte', pdfWidth / 2, margin + 5, { align: 'center' });
    
    let yPos = margin + 20;

    for (const sheet of sheetElements) {
      const canvas = await html2canvas(sheet, { 
          scale: 2, 
          useCORS: true, 
          backgroundColor: '#ffffff' 
      });

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
          <CuttingLayout result={result} isLoading={isLoading} error={error} layoutRef={layoutRef} />
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