import React, { useState, useEffect } from 'react';
import FlowChart from './components/FlowChart';
import './App.css';

function App() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [visualizationData, setVisualizationData] = useState(null);

  useEffect(() => {
    fetchVisualizationData();
  }, []);

  const fetchVisualizationData = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/visualization');
      if (!response.ok) {
        throw new Error('Failed to load visualization data');
      }
      const data = await response.json();
      setVisualizationData(data);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="app-loading">
        <div className="loading-spinner"></div>
        <p>Loading literature review data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app-error">
        <h2>Error Loading Data</h2>
        <p>{error}</p>
        <button onClick={fetchVisualizationData}>Retry</button>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Literature Review Visualizer</h1>
        <button onClick={fetchVisualizationData} className="refresh-btn">
          Refresh Data
        </button>
      </header>
      <main className="app-main">
        {visualizationData && <FlowChart data={visualizationData} />}
      </main>
    </div>
  );
}

export default App;




