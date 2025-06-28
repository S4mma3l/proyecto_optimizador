import React, { useState } from 'react';
import InputForm from './components/InputForm';
import CuttingLayout from './components/CuttingLayout';
import './App.css';
import { VscTools } from 'react-icons/vsc';

function App() {
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleOptimize = async (requestData) => {
    setIsLoading(true);
    setError('');
    setResult(null);
    try {
      const apiUrl = 'https://proyectooptimizador-production.up.railway.app/api/optimize';
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData),
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => response.text());
        const errorMsg = typeof errorBody === 'object' ? JSON.stringify(errorBody.detail) : errorBody;
        throw new Error(`Error ${response.status}: ${errorMsg}`);
      }
      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error("Error en la solicitud fetch:", err);
      setError("Error al conectar con la API. Por favor, revisa la consola.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <div className="header-left">
          <a href="https://www.pentestercr.com/" target="_blank" rel="noopener noreferrer" className="header-title-link">
            <VscTools size="1.6em" />
            <h1>Optimizador Pro</h1>
          </a>
        </div>
        
        {/* --- CABECERA DERECHA ACTUALIZADA --- */}
        <div className="header-right">
          <a href="https://s4mma3l.github.io/Pagina_de_valoracion/" target="_blank" rel="noopener noreferrer" className="developer-button">
            Sugerencias
          </a>
          <span className="header-separator">|</span>
          <a href="https://www.linkedin.com/in/pentestercr/" target="_blank" rel="noopener noreferrer" className="developer-button">
            Desarrollado por Ángel Hernández M. | Version 1.3
          </a>
        </div>

      </header>
      <main>
        <div className="controls-panel">
          <InputForm onSubmit={handleOptimize} isLoading={isLoading} />
        </div>
        <div className="layout-container">
          <CuttingLayout result={result} isLoading={isLoading} error={error} />
        </div>
      </main>
    </div>
  );
}

export default App;