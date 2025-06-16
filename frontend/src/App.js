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

  // --- FUNCIÓN DE OPTIMIZACIÓN CON LOGS DE DEPURACIÓN ---
  const handleOptimize = async (requestData) => {
    setIsLoading(true);
    setError('');
    setResult(null);

    try {
      // --- ¡LÍNEA A CORREGIR! ---
      // Reemplaza esta URL de ejemplo con la URL exacta y correcta de tu dashboard de Railway
      // que ya probaste y funcionó en Postman.
      const apiUrl = 'https://proyectooptimizador-production.up.railway.app/api/optimize'; 

      // --- LOGS DE DEPURACIÓN ---
      console.log("===================================");
      console.log("Iniciando solicitud a la API...");
      console.log("URL de destino:", apiUrl);
      console.log("Datos enviados:", JSON.stringify(requestData, null, 2));

      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json' 
        },
        body: JSON.stringify(requestData),
      });

      console.log("Respuesta recibida del servidor.");
      console.log("Status Code:", response.status);
      console.log("Response OK:", response.ok);

      if (!response.ok) {
        // Si la respuesta no es exitosa, intentamos leer el texto del error.
        const errorText = await response.text();
        console.error("Respuesta de error de la API:", errorText);
        throw new Error(`Error en la API (${response.status}). Ver consola para más detalles.`);
      }

      const data = await response.json();
      console.log("Datos recibidos y procesados correctamente:", data);
      console.log("===================================");
      setResult(data);

    } catch (err)
    {
      console.error("ERROR CATASTRÓFICO EN EL BLOQUE FETCH:", err);
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