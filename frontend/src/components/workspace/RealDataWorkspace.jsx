import { useEffect, useState } from 'react';
import { AlertTriangle, ArrowLeft, CheckCircle2, Database, FileUp, Play, ShieldCheck, TrendingUp } from 'lucide-react';
import EvidenceReportPanel from './EvidenceReportPanel';
import {
  createRecommendation,
  createRetailer,
  generateGeminiReport,
  getDatasets,
  getProducts,
  getRetailers,
  previewReport,
  runCausalAnalysis,
  uploadDataset,
  validateDataset,
} from '../../services/pricingPlatformService';

const money = (value) => (value == null ? '—' : `$${Number(value).toFixed(2)}`);

export default function RealDataWorkspace({ onBack, user }) {
  const [retailerName, setRetailerName] = useState('');
  const [retailerId, setRetailerId] = useState('');
  const [retailers, setRetailers] = useState([]);
  const [file, setFile] = useState(null);
  const [validation, setValidation] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [products, setProducts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [recommendation, setRecommendation] = useState(null);
  const [constraints, setConstraints] = useState({ minimum_margin: 15, maximum_price_increase: 20, maximum_price_decrease: 20 });
  const [report, setReport] = useState(null);
  const [question, setQuestion] = useState('Explain the verified pricing evidence and whether a recommendation is safe.');
  const [message, setMessage] = useState('Create a retailer workspace, then upload an authorised historical-sales CSV.');
  const [busy, setBusy] = useState(false);

  async function refreshProducts(id = retailerId) {
    const items = await getProducts(id);
    setProducts(items);
    setSelected(items[0] || null);
  }

  async function refreshDatasets(id = retailerId) {
    const items = await getDatasets(id);
    setDatasets(items);
  }

  useEffect(() => {
    let active = true;
    getRetailers()
      .then((items) => {
        if (!active) return;
        setRetailers(items);
        const savedId = localStorage.getItem('dpeci_retailer_id');
        const workspace = items.find((item) => item.id === savedId) || items[0] || null;
        setRetailerId(workspace?.id || '');
        if (workspace) localStorage.setItem('dpeci_retailer_id', workspace.id);
      })
      .catch((error) => active && setMessage(error.message));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!retailerId) return undefined;
    let active = true;
    Promise.all([getProducts(retailerId), getDatasets(retailerId)])
      .then(([productItems, datasetItems]) => {
        if (!active) return;
        setProducts(productItems);
        setSelected(productItems[0] || null);
        setDatasets(datasetItems);
      })
      .catch((error) => active && setMessage(error.message));
    return () => { active = false; };
  }, [retailerId]);

  async function runWork(action) {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  function handleCreate(event) {
    event.preventDefault();
    runWork(async () => {
      const retailer = await createRetailer(retailerName);
      localStorage.setItem('dpeci_retailer_id', retailer.id);
      localStorage.setItem('dpeci_retailer_name', retailer.name);
      setRetailers((items) => [...items, retailer]);
      setRetailerId(retailer.id);
      setAnalysis(null);
      setRecommendation(null);
      setReport(null);
      setMessage(`Workspace created for ${retailer.name}.`);
    });
  }

  function handleUpload(event) {
    event.preventDefault();
    if (!file) return;
    runWork(async () => {
      const result = await uploadDataset(retailerId, file);
      await Promise.all([refreshProducts(), refreshDatasets()]);
      setAnalysis(null);
      setRecommendation(null);
      setFile(null);
      setValidation(null);
      setMessage(`${result.valid_rows} valid observations were stored from ${result.source_filename}.`);
    });
  }

  function handleValidate() {
    if (!file) return;
    runWork(async () => {
      const result = await validateDataset(file);
      setValidation(result);
      setMessage(result.status === 'valid' ? 'Validation passed. You can now store this dataset.' : 'Validation found errors. Correct the CSV before storing it.');
    });
  }

  function handleAnalysis() {
    runWork(async () => {
      const result = await runCausalAnalysis(retailerId, selected.id);
      setAnalysis(result);
      setRecommendation(null);
      setMessage(result.status === 'blocked' ? result.limitations.join(' ') : 'Causal analysis completed.');
    });
  }

  function handleOptimisation() {
    runWork(async () => {
      const result = await createRecommendation(retailerId, selected.id, analysis.model_run_id, {
        minimum_margin: Number(constraints.minimum_margin) / 100,
        maximum_price_increase: Number(constraints.maximum_price_increase) / 100,
        maximum_price_decrease: Number(constraints.maximum_price_decrease) / 100,
      });
      setRecommendation(result);
      setMessage('Constrained price recommendation created from the verified causal run.');
    });
  }

  function handleReportPreview() {
    runWork(async () => {
      const result = await previewReport(retailerId, selected.id, question);
      setReport(result);
      setMessage('Grounded evidence preview generated. No LLM provider has been used.');
    });
  }

  function handleGeminiReport() {
    runWork(async () => {
      const result = await generateGeminiReport(retailerId, selected.id, question);
      setReport(result);
      setMessage('Gemini generated a report from retrieved verified evidence.');
    });
  }

  const diagnosticsPassed = Boolean(analysis?.diagnostics?.length) && analysis.diagnostics.every((check) => check.passed);
  const analysisSafe = analysis?.status === 'completed' && diagnosticsPassed && Number(analysis.ci_upper) < 0;

  return (
    <main className="app-container" style={{ paddingTop: 72, paddingBottom: 72, position: 'relative', zIndex: 1 }}>
      <button className="apple-button secondary" onClick={onBack} style={{ padding: '8px 14px', fontSize: 12 }}>
        <ArrowLeft className="h-3.5 w-3.5" /> Back
      </button>

      <div style={{ marginTop: 28, maxWidth: 980 }}>
        <span className="telemetry-label">LIVE DATA WORKSPACE</span>
        <h1 style={{ fontSize: 38, marginTop: 10, fontWeight: 600 }}>Build recommendations from your evidence.</h1>
        <p style={{ color: 'var(--text-secondary)', marginTop: 10 }}>
          Upload authorised historical data. The platform validates it, estimates causal price effects, and blocks unsafe recommendations.
        </p>
      </div>

      <p className="telemetry-label" style={{ marginTop: 18 }}>SIGNED IN AS {user?.email}</p>

      {!retailerId ? (
        <form onSubmit={handleCreate} className="apple-card liquid-glass" style={{ marginTop: 28, maxWidth: 560 }}>
          <Database className="h-5 w-5 text-sky-400" />
          <h2 style={{ marginTop: 14, fontSize: 18 }}>Create retailer workspace</h2>
          <input className="chat-input" value={retailerName} onChange={(event) => setRetailerName(event.target.value)} placeholder="Business name" required style={{ marginTop: 18, width: '100%' }} />
          <button className="apple-button" disabled={busy} style={{ marginTop: 14 }}>{busy ? 'Creating…' : 'Create workspace'}</button>
        </form>
      ) : (
        <>
          <section className="apple-card liquid-glass" style={{ marginTop: 28 }}>
            <span className="telemetry-label">ACTIVE RETAILER WORKSPACE</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              {retailers.map((retailer) => <button key={retailer.id} className="product-pill" onClick={() => { setRetailerId(retailer.id); setAnalysis(null); setRecommendation(null); setReport(null); localStorage.setItem('dpeci_retailer_id', retailer.id); }} style={{ borderColor: retailer.id === retailerId ? 'var(--accent-blue)' : undefined }}>{retailer.name}</button>)}
              <button className="apple-button secondary" onClick={() => { setRetailerId(''); setProducts([]); setDatasets([]); setSelected(null); setAnalysis(null); setRecommendation(null); setReport(null); }} style={{ padding: '8px 12px', fontSize: 12 }}>New workspace</button>
            </div>
          </section>
          <form onSubmit={handleUpload} className="apple-card liquid-glass" style={{ marginTop: 28 }}>
            <FileUp className="h-5 w-5 text-purple-400" />
            <h2 style={{ marginTop: 10, fontSize: 18 }}>Upload historical sales CSV</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 6 }}>Required: date, product_id, price, units_sold, unit_cost.</p>
            <input type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] || null); setValidation(null); }} style={{ marginTop: 14 }} />
            <button type="button" className="apple-button secondary" onClick={handleValidate} disabled={!file || busy} style={{ marginLeft: 12 }}>{busy ? 'Working…' : 'Validate file'}</button>
            <button className="apple-button" disabled={validation?.status !== 'valid' || busy} style={{ marginLeft: 8 }}>{busy ? 'Storing…' : 'Store validated data'}</button>
            {validation && <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--border-color)', display: 'grid', gap: 8 }}>
              <p style={{ color: validation.status === 'valid' ? 'var(--accent-emerald)' : 'var(--accent-orange)', fontSize: 13 }}>
                {validation.status === 'valid' ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />} {validation.status.toUpperCase()} · {validation.valid_rows}/{validation.total_rows} usable rows · {validation.product_count} products · {validation.eligible_product_count} analysis-eligible
              </p>
              {validation.date_start && <p style={{ color: 'var(--text-secondary)', fontSize: 12 }}>Coverage: {validation.date_start} to {validation.date_end}. Recognised fields: {Object.keys(validation.resolved_columns).join(', ')}.</p>}
              {validation.issues.map((issue, index) => <p key={`${issue.field}-${index}`} style={{ color: issue.severity === 'error' ? 'var(--accent-orange)' : 'var(--text-secondary)', fontSize: 12 }}>{issue.severity.toUpperCase()} · {issue.field}: {issue.message}</p>)}
            </div>}
          </form>

          <section className="apple-card liquid-glass" style={{ marginTop: 20 }}>
            <span className="telemetry-label">DATASET HISTORY</span>
            {datasets.length === 0 ? <p style={{ color: 'var(--text-secondary)', marginTop: 10, fontSize: 13 }}>No uploaded datasets yet. Validate and store your first authorised CSV above.</p> : <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>{datasets.map((dataset) => <div key={dataset.id} className="product-pill" style={{ padding: 12 }}><strong>{dataset.source_filename}</strong><span style={{ display: 'block', color: 'var(--text-secondary)', fontSize: 12, marginTop: 4 }}>{dataset.valid_rows}/{dataset.total_rows} valid rows · {dataset.status} · uploaded {new Date(dataset.created_at).toLocaleString()}</span></div>)}</div>}
          </section>

          <p className="telemetry-label" style={{ marginTop: 24 }}>{message}</p>

          {products.length > 0 && (
            <section style={{ marginTop: 28, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(300px, .8fr)', gap: 20 }}>
              <div className="apple-card liquid-glass">
                <h2 style={{ fontSize: 18 }}>Uploaded products</h2>
                <div style={{ marginTop: 16, display: 'grid', gap: 8 }}>
                  {products.map((product) => (
                    <button key={product.id} onClick={() => { setSelected(product); setAnalysis(null); setRecommendation(null); setReport(null); }} className="product-pill" style={{ textAlign: 'left', padding: 14, borderColor: selected?.id === product.id ? 'var(--accent-blue)' : undefined }}>
                      <strong>{product.name || product.external_id}</strong>
                      <span style={{ display: 'block', marginTop: 4, color: 'var(--text-secondary)', fontSize: 12 }}>{money(product.latest_price)} · {product.latest_demand ?? '—'} units · {product.latest_date || '—'}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="apple-card liquid-glass">
                <span className="telemetry-label">CAUSAL DECISION WORKBENCH</span>
                <h2 style={{ marginTop: 10, fontSize: 20 }}>{selected?.name || selected?.external_id}</h2>
                <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>Latest observed price {money(selected?.latest_price)} · unit cost {money(selected?.latest_unit_cost)} · demand {selected?.latest_demand ?? '—'} units</p>
                <button className="apple-button" onClick={handleAnalysis} disabled={busy || !selected} style={{ marginTop: 20 }}><Play className="h-4 w-4" /> {busy ? 'Running analysis…' : 'Run causal analysis'}</button>

                {analysis && (
                  <div style={{ marginTop: 20, fontSize: 13 }}>
                    <div style={{ padding: 14, borderRadius: 10, background: analysisSafe ? 'rgba(16,185,129,.10)' : 'rgba(249,115,22,.10)', border: `1px solid ${analysisSafe ? 'rgba(16,185,129,.35)' : 'rgba(249,115,22,.35)'}` }}>
                      <ShieldCheck className={`h-4 w-4 ${analysisSafe ? 'text-emerald-400' : 'text-orange-400'}`} />
                      <strong style={{ marginLeft: 8 }}>{analysisSafe ? 'SAFE TO OPTIMIZE' : 'OPTIMIZATION BLOCKED'}</strong>
                      <p style={{ color: 'var(--text-secondary)', marginTop: 6 }}>{analysisSafe ? 'The estimated effect is negative with all robustness checks passed.' : analysis.limitations?.join(' ') || 'One or more robustness checks did not pass.'}</p>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8, marginTop: 14 }}>
                      <div className="product-pill" style={{ padding: 10 }}><span className="telemetry-label">PRICE EFFECT</span><strong style={{ display: 'block', marginTop: 5 }}>{analysis.effect == null ? '—' : Number(analysis.effect).toFixed(3)}</strong><span style={{ color: 'var(--text-muted)', fontSize: 11 }}>units / price unit</span></div>
                      <div className="product-pill" style={{ padding: 10 }}><span className="telemetry-label">95% INTERVAL</span><strong style={{ display: 'block', marginTop: 5 }}>{analysis.ci_lower == null ? '—' : `${Number(analysis.ci_lower).toFixed(2)} to ${Number(analysis.ci_upper).toFixed(2)}`}</strong><span style={{ color: 'var(--text-muted)', fontSize: 11 }}>must stay below zero</span></div>
                      <div className="product-pill" style={{ padding: 10 }}><span className="telemetry-label">OBSERVATIONS</span><strong style={{ display: 'block', marginTop: 5 }}>{analysis.observations}</strong><span style={{ color: 'var(--text-muted)', fontSize: 11 }}>records used</span></div>
                    </div>
                    <div style={{ marginTop: 18 }}><span className="telemetry-label">ROBUSTNESS CHECKS</span>{analysis.diagnostics?.map((check) => <div key={check.name} style={{ marginTop: 8, padding: 10, borderLeft: `3px solid ${check.passed ? 'var(--accent-emerald)' : 'var(--accent-orange)'}`, background: 'rgba(255,255,255,.025)' }}><strong style={{ color: check.passed ? 'var(--accent-emerald)' : 'var(--accent-orange)', fontSize: 12 }}>{check.passed ? 'PASS' : 'BLOCKED'} · {check.name.replaceAll('_', ' ')}</strong><p style={{ color: 'var(--text-secondary)', marginTop: 4 }}>{check.message}</p></div>)}</div>
                    {analysisSafe && <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-color)' }}>
                      <span className="telemetry-label">PRICE GUARDRAILS</span>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8, marginTop: 10 }}>{[['minimum_margin', 'Minimum margin'], ['maximum_price_increase', 'Max increase'], ['maximum_price_decrease', 'Max decrease']].map(([key, label]) => <label key={key} style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{label}<input className="chat-input" style={{ width: '100%', marginTop: 5 }} type="number" min="0" max="99" value={constraints[key]} onChange={(event) => setConstraints((current) => ({ ...current, [key]: event.target.value }))} /><span style={{ fontSize: 10 }}>%</span></label>)}</div>
                      <button className="apple-button" onClick={handleOptimisation} disabled={busy} style={{ marginTop: 14 }}><TrendingUp className="h-4 w-4" /> Optimize within guardrails</button>
                    </div>}
                  </div>
                )}

                {recommendation && (
                  <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-color)' }}>
                    <span className="telemetry-label">RECOMMENDATION</span>
                    <p style={{ fontSize: 25, marginTop: 6, color: 'var(--accent-emerald)' }}>{money(recommendation.recommended_price)}</p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Expected profit: {money(recommendation.expected_profit)}</p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>Expected demand: {Number(recommendation.expected_demand).toFixed(1)} units</p>
                    <p style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 8 }}>Based on the selected causal run and the guardrails shown above.</p>
                  </div>
                )}
              </div>
            </section>
          )}

          <EvidenceReportPanel
            selected={selected}
            question={question}
            onQuestionChange={setQuestion}
            onPreview={handleReportPreview}
            onGenerate={handleGeminiReport}
            report={report}
            busy={busy}
          />
        </>
      )}
    </main>
  );
}
