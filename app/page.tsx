'use client';

/* eslint-disable @next/next/no-img-element -- previews include local object URLs and a separate local API origin */

import { DragEvent, useCallback, useEffect, useRef, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type EventItem = { stage: string; progress: number; message: string; at: string; error?: boolean };
type ChainVerification = { matches: boolean; exists: boolean; tamperDetected?: boolean };
type Result = {
  caseId: string;
  capturedAt: string;
  trustScore: number;
  media: { input: string; face: string; annotated: string };
  face: {
    dimensions: number; detectionConfidence: number; faceCount: number; boundingBox: number[];
    embeddingHash: string; vectorPreview: number[]; model: string;
  };
  match: {
    postUrl: string; postTitle: string; platform: string; matchType: string; queryType: string;
    provider: string; providerScore: number; faceSimilarity: number | null; identityConfirmed: boolean;
    matchedImageUrl: string | null; socialPostsFound: number;
    webEntities: { description: string; score?: number }[];
  };
  evidence: { evidenceHash: string; sourceHash: string; payloadPath: string };
  blockchain: {
    verified: boolean; network: string; chainId: number; contractAddress: string;
    transactionHash: string | null; blockNumber: number | null; blockHash: string | null;
    submitter: string; anchoredAt: number;
  };
  verification: ChainVerification;
};
type Job = {
  caseId: string; filename: string; status: 'queued' | 'running' | 'completed' | 'failed';
  stage: string; progress: number; message: string; events: EventItem[]; result: Result | null; error: string | null;
};
type Health = { ok: boolean; searchConfigured: boolean; searchProvider: string; chain: { ok?: boolean; chainId?: number; blockNumber?: number; contractAddress?: string } };

const pipelineSteps = [
  { id: 'face', number: '01', label: 'Face encode', detail: 'YuNet · SFace 128D', threshold: 12 },
  { id: 'search', number: '02', label: 'Reverse search', detail: 'Google Vision Web', threshold: 42 },
  { id: 'chain', number: '03', label: 'Chain seal', detail: 'Solidity · EVM 31337', threshold: 76 },
  { id: 'verify', number: '04', label: 'Re-verify', detail: 'Contract read-back', threshold: 92 },
];

function shortHash(value?: string | null, left = 10, right = 8) {
  if (!value) return '—';
  return `${value.slice(0, left)}…${value.slice(-right)}`;
}

function timeLabel(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [dragging, setDragging] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [tab, setTab] = useState<'overview' | 'evidence' | 'ledger'>('overview');
  const [notice, setNotice] = useState('');
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/health`).then((response) => response.json()).then(setHealth).catch(() => setHealth(null));
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  const chooseFile = (next: File | undefined) => {
    if (!next) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(next.type)) {
      setNotice('Use a JPEG, PNG, or WEBP image.');
      return;
    }
    if (next.size > 10 * 1024 * 1024) {
      setNotice('The image must be under 10 MB.');
      return;
    }
    if (preview) URL.revokeObjectURL(preview);
    setFile(next);
    setPreview(URL.createObjectURL(next));
    setJob(null);
    setNotice('');
    setTab('overview');
  };

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files[0]);
  };

  const poll = useCallback(async function pollCase(caseId: string) {
    try {
      const response = await fetch(`${API_URL}/api/investigations/${caseId}`, { cache: 'no-store' });
      const next: Job = await response.json();
      setJob(next);
      if (next.status === 'queued' || next.status === 'running') {
        pollRef.current = setTimeout(() => pollCase(caseId), 850);
      }
    } catch {
      setNotice('Lost contact with the pipeline API. Is it running on port 8000?');
    }
  }, []);

  const start = async () => {
    if (!file) return;
    setNotice('');
    const body = new FormData();
    body.append('image', file);
    try {
      const response = await fetch(`${API_URL}/api/investigations`, { method: 'POST', body });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Could not start the investigation.');
      setJob(payload);
      poll(payload.caseId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not reach the pipeline API.');
    }
  };

  const verify = async (tamper = false) => {
    if (!job?.result) return;
    setVerifying(true);
    try {
      const endpoint = tamper ? 'tamper-check' : 'verify';
      const response = await fetch(`${API_URL}/api/investigations/${job.caseId}/${endpoint}`, { method: 'POST' });
      const result: ChainVerification = await response.json();
      setNotice(tamper
        ? (result.tamperDetected ? 'Tamper test passed: modified evidence was rejected by the contract.' : 'Unexpected: modified evidence was accepted.')
        : (result.matches ? 'On-chain record matches the original evidence exactly.' : 'Verification mismatch detected.'));
    } catch {
      setNotice('Could not reach the local EVM verification service.');
    } finally {
      setVerifying(false);
    }
  };

  const copy = async (value: string, label: string) => {
    await navigator.clipboard.writeText(value);
    setNotice(`${label} copied.`);
  };

  const reset = () => {
    if (preview) URL.revokeObjectURL(preview);
    if (pollRef.current) clearTimeout(pollRef.current);
    setFile(null); setPreview(''); setJob(null); setNotice(''); setTab('overview');
  };

  const result = job?.result;
  const running = job?.status === 'queued' || job?.status === 'running';

  return (
    <main className="app-shell">
      <div className="ambient ambient-one" /><div className="ambient ambient-two" />
      <header className="topbar">
        <a className="brand" href="#" aria-label="ProofFace home"><span className="brand-mark"><span /></span><span>PROOF<span>FACE</span></span></a>
        <div className="network-pill"><i className={health?.chain?.ok ? '' : 'offline'} /> LOCAL EVM <span>CHAIN {health?.chain?.chainId || 31337}</span></div>
        <div className="top-actions"><span className={`service-dot ${health?.searchConfigured ? 'online' : ''}`}>{health?.searchConfigured ? 'SEARCH READY' : 'API KEY NEEDED'}</span><button className="icon-button" aria-label="Reset investigation" onClick={reset}>↻</button></div>
      </header>

      <section className={`hero ${job ? 'hero-compact' : ''}`}>
        <div className="eyebrow"><span>◆</span> VERIFIABLE IDENTITY INTELLIGENCE</div>
        <h1>From face to <em>proof.</em></h1>
        <p>Discover where an image appears online, validate the match, and anchor a reproducible fingerprint to an immutable ledger.</p>
      </section>

      {!result ? (
        <section className="workspace-grid">
          <div className="pipeline-card">
            <div className="card-heading"><div><span className="section-kicker">NEW INVESTIGATION</span><h2>{running ? 'Building the evidence trail' : 'Start with a face scan'}</h2></div><span className="case-id">{job ? `CASE / ${job.caseId.toUpperCase()}` : 'CASE / DRAFT'}</span></div>

            {!running ? (
              <>
                <button className={`dropzone ${file ? 'has-file' : ''} ${dragging ? 'dragging' : ''}`} onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
                  <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => chooseFile(event.target.files?.[0])} hidden />
                  <span className="scan-corners"><i /><i /><i /><i /></span>
                  {preview ? <img className="selected-preview" src={preview} alt="Selected face scan" /> : <span className="face-glyph">⌾</span>}
                  <strong>{file?.name || 'Drop a portrait here'}</strong>
                  <small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · ready for biometric encoding` : 'or click to browse · JPEG, PNG, WEBP · max 10 MB'}</small>
                  <span className="select-file">{file ? 'CHANGE IMAGE' : 'SELECT IMAGE'} <b>↗</b></span>
                </button>
                <div className="privacy-note"><span>◇</span><p><strong>Controlled disclosure</strong>The 128D biometric vector remains local. The face crop and source image are sent only to the configured reverse-image provider; the chain stores fingerprints, not biometric data.</p></div>
                <button className="run-button" disabled={!file} onClick={start}><span>RUN VERIFICATION</span><b>→</b></button>
              </>
            ) : (
              <div className="scanner-view">
                <div className="scan-image"><img src={preview} alt="Face currently being verified" /><i className="scan-line" /><span className="scan-grid" /><b>{job.progress}%</b></div>
                <div className="activity-panel">
                  <span className="section-kicker">LIVE ANALYSIS</span><h3>{job.message}</h3>
                  <div className="progress-track"><i style={{ width: `${job.progress}%` }} /></div>
                  <div className="event-log">{job.events.slice(-4).map((item, index) => <div key={`${item.at}-${index}`} className={item.error ? 'error' : ''}><time>{timeLabel(item.at)}</time><span>{item.message}</span></div>)}</div>
                </div>
              </div>
            )}
            {job?.status === 'failed' && <div className="error-card"><span>!</span><div><strong>Pipeline stopped at {job.stage}</strong><p>{job.error}</p></div><button onClick={() => setJob(null)}>TRY AGAIN</button></div>}
          </div>

          <aside className="process-card">
            <div className="process-title"><span>PIPELINE</span><b>{running ? 'RUNNING' : 'READY'}</b></div>
            <div className="step-list">
              {pipelineSteps.map((step, index) => {
                const active = !!job && job.progress >= step.threshold;
                const done = !!job && (job.progress >= (pipelineSteps[index + 1]?.threshold ?? 101) || job.status === 'completed');
                return <div className={`step ${active ? 'active' : ''} ${done ? 'done' : ''}`} key={step.number}><div className="step-track"><span>{done ? '✓' : step.number}</span>{index < pipelineSteps.length - 1 && <i />}</div><div><strong>{step.label}</strong><small>{step.detail}</small></div><b>{active ? (done ? '●' : '◉') : '○'}</b></div>;
              })}
            </div>
            <div className="trust-score"><div className="score-ring" style={{ '--score': `${job?.progress || 0}%` } as React.CSSProperties}><span>{job ? job.progress : '—'}</span></div><div><span>PIPELINE STATUS</span><strong>{job ? job.stage.toUpperCase() : 'Awaiting evidence'}</strong><small>{job?.message || 'Trust score is calculated after cross-validation.'}</small></div></div>
          </aside>
        </section>
      ) : (
        <section className="results-shell">
          <div className="result-header">
            <div><span className="section-kicker">VERIFICATION COMPLETE</span><h2>Evidence sealed. Match confirmed.</h2><p>Case {result.caseId.toUpperCase()} · {new Date(result.capturedAt).toLocaleString()}</p></div>
            <div className="verdict"><div className="verdict-score">{result.trustScore}<small>/100</small></div><div><span>TRUST SCORE</span><strong>HIGH CONFIDENCE</strong><small>Search + face + chain signals</small></div></div>
          </div>

          <div className="result-tabs" role="tablist">
            {(['overview', 'evidence', 'ledger'] as const).map((item) => <button role="tab" aria-selected={tab === item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)} key={item}>{item.toUpperCase()}</button>)}
            <button className="new-case" onClick={reset}>＋ NEW CASE</button>
          </div>

          {tab === 'overview' && <div className="overview-grid">
            <article className="result-card face-card"><div className="result-card-title"><span>01 / BIOMETRIC SIGNAL</span><b>FACE ENCODED</b></div><div className="face-visual"><img src={result.media.annotated} alt="Detected face with landmarks" /><span className="scan-corners"><i /><i /><i /><i /></span><div className="face-badge"><strong>{(result.face.detectionConfidence * 100).toFixed(1)}%</strong><small>DETECTION</small></div></div><div className="metric-row"><div><small>MODEL</small><strong>SFace / YuNet</strong></div><div><small>VECTOR</small><strong>{result.face.dimensions}D</strong></div><div><small>FACES</small><strong>{result.face.faceCount}</strong></div></div></article>
            <article className="result-card match-card"><div className="result-card-title"><span>02 / SOCIAL DISCOVERY</span><b>MATCH FOUND</b></div><div className="platform-mark">{result.match.platform.slice(0, 2).toUpperCase()}</div><span className="platform-label">{result.match.platform} · PUBLIC POST</span><h3>{result.match.postTitle}</h3><a href={result.match.postUrl} target="_blank" rel="noreferrer">{result.match.postUrl}<b>↗</b></a><div className="match-signals"><div><i /><span>Provider {result.match.matchType} match</span><b>{Math.round(result.match.providerScore * 100)}%</b></div><div><i className={result.match.identityConfirmed ? '' : 'soft'} /><span>{result.match.identityConfirmed ? 'SFace identity confirmed' : 'Provider visual confirmation'}</span><b>{result.match.faceSimilarity ? result.match.faceSimilarity.toFixed(3) : 'N/A'}</b></div><div><i /><span>Post URL classification</span><b>PASS</b></div></div></article>
            <article className="result-card chain-card"><div className="result-card-title"><span>03 / IMMUTABLE RECORD</span><b>ON-CHAIN</b></div><div className="chain-seal"><span>◆</span><i /><b>VERIFIED</b></div><div className="chain-fields"><label>NETWORK <strong>{result.blockchain.network} · {result.blockchain.chainId}</strong></label><label>BLOCK <strong>#{result.blockchain.blockNumber ?? 'persisted'}</strong></label><label>CONTRACT <button onClick={() => copy(result.blockchain.contractAddress, 'Contract')}>{shortHash(result.blockchain.contractAddress)}</button></label><label>TRANSACTION <button onClick={() => result.blockchain.transactionHash && copy(result.blockchain.transactionHash, 'Transaction')}>{shortHash(result.blockchain.transactionHash)}</button></label></div><div className="verify-actions"><button onClick={() => verify(false)} disabled={verifying}>↻ VERIFY RECORD</button><button className="tamper" onClick={() => verify(true)} disabled={verifying}>⚠ TAMPER TEST</button></div></article>
          </div>}

          {tab === 'evidence' && <div className="detail-layout"><article className="detail-card"><div className="result-card-title"><span>CANONICAL EVIDENCE</span><b>SHA-256</b></div><h3>Every discovery input is fingerprinted.</h3><p>The payload includes the original image hash, local embedding hash, model versions, detection geometry, search provider, matching post, and match signals. Changing any byte produces a different fingerprint.</p><HashField label="EVIDENCE HASH" value={result.evidence.evidenceHash} onCopy={copy} /><HashField label="SOURCE HASH" value={result.evidence.sourceHash} onCopy={copy} /><HashField label="LOCAL EMBEDDING HASH" value={result.face.embeddingHash} onCopy={copy} /></article><article className="detail-card vector-card"><div className="result-card-title"><span>VECTOR PREVIEW</span><b>LOCAL ONLY</b></div><div className="vector-bars">{result.face.vectorPreview.map((value, index) => <div key={index}><span>{String(index).padStart(2, '0')}</span><i><b style={{ width: `${Math.min(100, Math.abs(value) * 500)}%` }} /></i><code>{value.toFixed(5)}</code></div>)}</div><p>Only the embedding hash is part of the evidence payload. The raw vector never leaves this machine or reaches the blockchain.</p></article></div>}

          {tab === 'ledger' && <div className="detail-layout ledger-layout"><article className="detail-card"><div className="result-card-title"><span>CONTRACT RECEIPT</span><b>MINED</b></div><div className="receipt-status"><span>✓</span><div><strong>Transaction finalized</strong><small>EvidenceAnchored event emitted and read back</small></div></div><div className="receipt-grid"><label>Chain ID <strong>{result.blockchain.chainId}</strong></label><label>Block number <strong>{result.blockchain.blockNumber ?? 'persisted record'}</strong></label><label>Submitter <code>{result.blockchain.submitter}</code></label><label>Contract <code>{result.blockchain.contractAddress}</code></label><label>Transaction <code>{result.blockchain.transactionHash || 'Reused existing evidence record'}</code></label></div></article><article className="detail-card verify-card"><div className="result-card-title"><span>INDEPENDENT CHECK</span><b>PASS</b></div><div className="logic-flow"><span>LOCAL DATA</span><i>SHA-256</i><span>CONTRACT READ</span><i>===</i><span className="pass">MATCH</span></div><p>The API recomputes the source fingerprint, calls the Solidity <code>verify()</code> view function, and compares the stored URL and content hash.</p><button className="large-verify" onClick={() => verify(false)} disabled={verifying}>{verifying ? 'CHECKING…' : 'RUN VERIFICATION AGAIN'} <b>→</b></button><button className="text-action" onClick={() => verify(true)} disabled={verifying}>Demonstrate rejection of modified evidence</button></article></div>}
        </section>
      )}

      {notice && <button className="toast" onClick={() => setNotice('')}><span>{notice.includes('passed') || notice.includes('matches') || notice.includes('copied') ? '✓' : '!'}</span>{notice}<b>×</b></button>}
      <footer><span>OPENCV SFACE</span><i /><span>GOOGLE VISION</span><i /><span>SOLIDITY EVM</span><b>Evidence, not assumptions.</b></footer>
    </main>
  );
}

function HashField({ label, value, onCopy }: { label: string; value: string; onCopy: (value: string, label: string) => void }) {
  return <div className="hash-field"><span>{label}</span><code>{value}</code><button onClick={() => onCopy(value, label)}>COPY</button></div>;
}
