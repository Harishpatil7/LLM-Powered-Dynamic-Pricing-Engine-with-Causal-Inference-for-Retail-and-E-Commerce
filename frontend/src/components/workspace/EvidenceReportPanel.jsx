import { Bot, FileSearch, Loader2, Sparkles } from 'lucide-react';

export default function EvidenceReportPanel({
  selected,
  question,
  onQuestionChange,
  onPreview,
  onGenerate,
  report,
  isBusy,
  actionLoading,
}) {
  const isPreviewLoading = actionLoading === 'preview_report';
  const isGenerateLoading = actionLoading === 'gemini_report';

  return (
    <section className="apple-card liquid-glass" style={{ marginTop: 28 }}>
      <span className="telemetry-label">EVIDENCE & GEMINI REPORTS</span>
      <h2 style={{ marginTop: 10, fontSize: 22 }}>Ask about verified pricing evidence</h2>
      <p style={{ color: 'var(--text-secondary)', marginTop: 8, fontSize: 13, maxWidth: 720 }}>
        {selected ? `Reports are scoped to ${selected.name || selected.external_id}. The system retrieves only your stored dataset, causal-analysis, and recommendation evidence.` : 'Select a real uploaded product before requesting evidence.'}
      </p>
      <label style={{ display: 'block', marginTop: 18, color: 'var(--text-secondary)', fontSize: 12 }}>Report question
        <textarea className="chat-input" value={question} onChange={(event) => onQuestionChange(event.target.value)} disabled={!selected || isBusy} style={{ width: '100%', minHeight: 82, marginTop: 6, resize: 'vertical' }} />
      </label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
        <button className="apple-button secondary" onClick={onPreview} disabled={!selected || isBusy || question.trim().length < 3}>
          {isPreviewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}
          {' '}
          {isPreviewLoading ? 'Retrieving…' : 'Retrieve verified evidence'}
        </button>
        <button className="apple-button" onClick={onGenerate} disabled={!selected || isBusy || question.trim().length < 3}>
          {isGenerateLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {' '}
          {isGenerateLoading ? 'Generating…' : 'Generate Gemini report'}
        </button>
      </div>
      <p style={{ marginTop: 10, color: 'var(--text-muted)', fontSize: 11 }}>Gemini cannot add unverified facts or create a recommendation when the retrieved causal evidence says it is unsafe.</p>

      {report && <div style={{ marginTop: 24, paddingTop: 18, borderTop: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Bot className="h-4 w-4 text-sky-400" /><span className="telemetry-label">{report.report_type.replaceAll('_', ' ')}</span></div>
        <div style={{ whiteSpace: 'pre-wrap', color: 'var(--text-secondary)', lineHeight: 1.65, fontSize: 14, marginTop: 12 }}>{report.answer}</div>
        {report.warning && <p style={{ color: 'var(--accent-orange)', fontSize: 12, marginTop: 12 }}>{report.warning}</p>}
        <div style={{ marginTop: 18 }}><span className="telemetry-label">RETRIEVED VERIFIED SOURCES</span>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8, marginTop: 10 }}>{report.sources.map((source) => <div className="product-pill" key={source.id} style={{ padding: 10 }}><strong style={{ fontSize: 12 }}>{source.title}</strong><span style={{ display: 'block', marginTop: 5, color: 'var(--text-muted)', fontSize: 11 }}>{source.source_type.replaceAll('_', ' ')} · relevance {Math.round(source.score * 100)}%</span></div>)}</div>
        </div>
      </div>}
    </section>
  );
}

