import { useState, useEffect, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { Activity, AlertTriangle, ShieldCheck, Zap, RefreshCw, ServerCrash, Clock } from 'lucide-react';
import './index.css'; // Make sure styles are imported

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const API_BASE = 'http://127.0.0.1:8000';

function App() {
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState({ login: [], payment: [], search: [] });
  const [narrations, setNarrations] = useState([]);
  const [isBackendOnline, setIsBackendOnline] = useState(true);
  const narrationsEndRef = useRef(null);

  // Fetch summary data
  const fetchSummary = async () => {
    try {
      const res = await fetch(`${API_BASE}/metrics/summary?minutes=10`);
      if (!res.ok) throw new Error('Network response was not ok');
      const data = await res.json();
      setSummary(data);
      setIsBackendOnline(true);
    } catch (error) {
      console.error("Failed to fetch summary", error);
      setIsBackendOnline(false);
    }
  };

  // Fetch history data for charts
  const fetchHistory = async () => {
    try {
      const services = ['login', 'payment', 'search'];
      const historyData = {};
      for (const svc of services) {
        const res = await fetch(`${API_BASE}/metrics/history?service=${svc}&minutes=5`);
        if (res.ok) {
          const data = await res.json();
          historyData[svc] = data.metrics.slice(-50); // Get last 50 points
        }
      }
      setHistory(historyData);
    } catch (error) {
      console.error("Failed to fetch history", error);
    }
  };

  // Fetch narrations
  const fetchNarrations = async () => {
    try {
      const res = await fetch(`${API_BASE}/narrations/recent?limit=10`);
      if (res.ok) {
        const data = await res.json();
        setNarrations(data.reverse()); // Show oldest top, newest bottom
      }
    } catch (error) {
      console.error("Failed to fetch narrations", error);
    }
  };

  // Auto-scroll narrations
  useEffect(() => {
    narrationsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [narrations]);

  // Polling loops
  useEffect(() => {
    fetchSummary();
    fetchHistory();
    fetchNarrations();

    const summaryInterval = setInterval(fetchSummary, 3000);
    const historyInterval = setInterval(fetchHistory, 5000);
    const narrationsInterval = setInterval(fetchNarrations, 5000);

    return () => {
      clearInterval(summaryInterval);
      clearInterval(historyInterval);
      clearInterval(narrationsInterval);
    };
  }, []);

  // Chaos controls
  const setChaos = async (service, mode) => {
    try {
      await fetch(`${API_BASE}/admin/chaos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service, mode })
      });
      fetchSummary(); // immediate refresh
    } catch (error) {
      console.error("Failed to set chaos", error);
    }
  };

  const resetChaos = async () => {
    try {
      await fetch(`${API_BASE}/admin/chaos/reset`, { method: 'POST' });
      fetchSummary();
    } catch (error) {
      console.error("Failed to reset chaos", error);
    }
  };

  // Chart configuration
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 0 },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { position: 'top', labels: { color: '#e6edf3' } },
      tooltip: { mode: 'index', intersect: false }
    },
    scales: {
      x: { display: false },
      y: { 
        beginAtZero: true, 
        grid: { color: '#30363d' },
        ticks: { color: '#7d8590' },
        title: { display: true, text: 'Latency (ms)', color: '#7d8590' }
      }
    }
  };

  // Format data for Chart.js
  const chartData = {
    labels: history.login.map(m => new Date(m.timestamp).toLocaleTimeString()),
    datasets: [
      {
        label: 'Login',
        data: history.login.map(m => m.latency_ms),
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88, 166, 255, 0.1)',
        borderWidth: 2,
        tension: 0.3,
        fill: true
      },
      {
        label: 'Payment',
        data: history.payment.map(m => m.latency_ms),
        borderColor: '#2ea043',
        backgroundColor: 'rgba(46, 160, 67, 0.1)',
        borderWidth: 2,
        tension: 0.3,
        fill: true
      },
      {
        label: 'Search',
        data: history.search.map(m => m.latency_ms),
        borderColor: '#d29922',
        backgroundColor: 'rgba(210, 153, 34, 0.1)',
        borderWidth: 2,
        tension: 0.3,
        fill: true
      }
    ]
  };

  if (!isBackendOnline) {
    return (
      <div className="dashboard-container" style={{ alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <div className="panel" style={{ textAlign: 'center', maxWidth: '400px' }}>
          <ServerCrash size={48} color="var(--color-danger)" style={{ margin: '0 auto' }} />
          <h2 style={{ marginTop: '1rem' }}>Backend Offline</h2>
          <p style={{ color: 'var(--text-muted)' }}>Could not connect to the Degradation Detective API at {API_BASE}.</p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.5rem' }}>Make sure you've run: <code>uvicorn backend.fake_services:app --reload</code> and <code>python backend/watcher.py</code></p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      {/* Header */}
      <header className="header">
        <div className="header-title">
          <Activity size={28} color="var(--color-accent)" />
          <h1>Degradation Detective</h1>
        </div>
        <div className="header-status">
          <div className="pulse"></div>
          Live Observability
        </div>
      </header>

      {/* Service Cards */}
      <div className="services-grid">
        {summary && Object.values(summary.services).map((svc) => (
          <div key={svc.service_name} className="service-card">
            <div className="service-header">
              <span className="service-name">{svc.service_name}</span>
              <span className={`status-badge status-${svc.status}`}>
                {svc.status}
              </span>
            </div>
            
            <div className="metric-row">
              <span className="metric-label">Average Latency</span>
              <span className="metric-value">{svc.average_latency_ms.toFixed(0)} ms</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Error Rate (10m)</span>
              <span className="metric-value">{svc.error_rate_percent.toFixed(1)}%</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Latest Status</span>
              <span className="metric-value">
                {svc.latest_metric ? (
                  svc.latest_metric.is_error ? (
                    <span style={{color: 'var(--color-danger)'}}>{svc.latest_metric.status_code} Error</span>
                  ) : (
                    <span style={{color: 'var(--color-success)'}}>{svc.latest_metric.status_code} OK</span>
                  )
                ) : 'N/A'}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="main-grid">
        {/* Left Column: Charts */}
        <div className="panel">
          <div className="panel-title">
            <Activity size={18} /> Latency Telemetry (Live)
          </div>
          <div className="chart-container">
            {history.login.length > 0 ? (
              <Line options={chartOptions} data={chartData} />
            ) : (
              <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)'}}>
                Loading telemetry data...
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Chaos Controls & Narrations */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          {/* Chaos Panel */}
          <div className="panel">
            <div className="panel-title">
              <AlertTriangle size={18} color="var(--color-warning)" /> Scenario Simulator
            </div>
            <div className="chaos-grid">
              <button className="btn btn-warning" onClick={() => setChaos('login', 'slow')}>
                <Clock size={16} /> Slow Login
              </button>
              <button className="btn btn-danger" onClick={() => setChaos('payment', 'errors')}>
                <ServerCrash size={16} /> Break Payment
              </button>
              <button className="btn btn-danger" onClick={() => setChaos('search', 'both')}>
                <Zap size={16} /> Overload Search
              </button>
              <button className="btn btn-success" onClick={resetChaos}>
                <ShieldCheck size={16} /> Fix All Services
              </button>
            </div>
          </div>

          {/* Narration Feed */}
          <div className="panel" style={{ flexGrow: 1 }}>
            <div className="panel-title">
              <ShieldCheck size={18} color="var(--color-accent)" /> SRE AI Insights
            </div>
            <div className="narrations-list">
              {narrations.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '2rem' }}>
                  No recent incidents. System is healthy.
                </div>
              ) : (
                narrations.map(narration => (
                  <div key={narration.id} className={`narration-item ${narration.severity}`}>
                    <div className="narration-header">
                      <span>{narration.service_name.toUpperCase()} - {narration.severity.toUpperCase()}</span>
                      <span>{new Date(narration.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <div className="narration-summary">
                      {narration.summary}
                    </div>
                    <div className="narration-details">
                      <div><strong>Root Cause:</strong> {narration.root_cause}</div>
                      <div><strong>Action:</strong> {narration.next_action}</div>
                    </div>
                  </div>
                ))
              )}
              <div ref={narrationsEndRef} />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

export default App;
