import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  AlertTriangle,
  Shield,
  ShieldCheck,
  ShieldX,
  Lock,
  Eye,
  FileText,
  ChevronDown,
  ChevronUp,
  Filter,
  BarChart3,
  ExternalLink,
} from 'lucide-react';
import { analysisApi, handleApiError } from '../api';
import { Card, Button, Spinner, EmptyState } from '../components/ui';
import type {
  AnalysisResponse,
  PairAnalysisRow,
  ExpertNotebookPayload,
  ExpertSummaryReport,
  ExpertEvidence,
} from '../types';

// ─── Hebrew labels ──────────────────────────────────────────────────

const OUTCOME_LABELS: Record<string, string> = {
  TRUE_CONTRADICTION: 'סתירה אמיתית',
  APPARENT_TENSION_RESOLVABLE: 'מתח לכאורה (ניתן ליישוב)',
  DISAGREEMENT_BETWEEN_PARTIES: 'מחלוקת בין צדדים',
  ROLE_OR_ATTRIBUTION_MISMATCH: 'אי-התאמה בייחוס/תפקיד',
  PLANE_MISMATCH: 'חוסר התאמה במישור',
  TIME_OR_STAGE_SHIFT: 'שינוי זמן/שלב',
  AMBIGUITY_OR_VAGUENESS: 'עמימות',
  INSUFFICIENT_CONTEXT: 'הקשר חסר',
  DUPLICATE_OR_RESTATEMENT: 'כפילות/ניסוח מחדש',
  UNKNOWN: 'לא ידוע',
};

const OUTCOME_COLORS: Record<string, string> = {
  TRUE_CONTRADICTION: 'bg-red-100 text-red-800 border-red-200',
  APPARENT_TENSION_RESOLVABLE: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  DISAGREEMENT_BETWEEN_PARTIES: 'bg-orange-100 text-orange-800 border-orange-200',
  ROLE_OR_ATTRIBUTION_MISMATCH: 'bg-purple-100 text-purple-800 border-purple-200',
  PLANE_MISMATCH: 'bg-blue-100 text-blue-800 border-blue-200',
  TIME_OR_STAGE_SHIFT: 'bg-teal-100 text-teal-800 border-teal-200',
  AMBIGUITY_OR_VAGUENESS: 'bg-slate-100 text-slate-800 border-slate-200',
  INSUFFICIENT_CONTEXT: 'bg-gray-100 text-gray-800 border-gray-200',
  DUPLICATE_OR_RESTATEMENT: 'bg-gray-100 text-gray-600 border-gray-200',
};

const SPEAKER_LABEL: Record<string, string> = {
  finding: 'קביעה שיפוטית',
  party_claim: 'טענת צד',
  quote: 'ציטוט',
  law_citation: 'הפניה לחוק',
  opinion: 'דעה',
};

const SPEAKER_COLOR: Record<string, string> = {
  finding: 'bg-green-100 text-green-700 border-green-200',
  party_claim: 'bg-orange-100 text-orange-700 border-orange-200',
  quote: 'bg-blue-100 text-blue-700 border-blue-200',
  law_citation: 'bg-purple-100 text-purple-700 border-purple-200',
  opinion: 'bg-slate-100 text-slate-700 border-slate-200',
};

const PLANE_LABEL: Record<string, string> = {
  FACT: 'עובדה',
  LAW: 'חוק',
  OPINION: 'דעה',
  PROCEDURAL: 'פרוצדורלי',
};

const PLANE_COLOR: Record<string, string> = {
  FACT: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  LAW: 'bg-violet-100 text-violet-700 border-violet-200',
  OPINION: 'bg-amber-100 text-amber-700 border-amber-200',
  PROCEDURAL: 'bg-sky-100 text-sky-700 border-sky-200',
};

const GATE_LABELS: Record<string, string> = {
  context_present: 'הקשר קיים',
  speaker_mode_ok: 'מצב דובר תקין',
  plane_match: 'התאמת מישור',
  time_match: 'התאמת זמן',
  scope_match: 'התאמת תחולה',
  reconciliation_failed: 'יישוב נכשל',
};

const ATTRIBUTION_PATTERNS = [
  /לטענת\s/g, /נטען\s+כי/g, /טען\s+כי/g, /עשויים\s+לטעון/g,
  /עשוי\s+לטעון/g, /לכאורה/g, /דומה\s+כי/g, /לדברי\s/g,
  /לגרסת\s/g, /may\s+argue/gi, /allegedly/gi,
];

function highlightAttribution(text: string): React.ReactNode {
  let parts: { text: string; isAttr: boolean }[] = [{ text, isAttr: false }];
  for (const pat of ATTRIBUTION_PATTERNS) {
    const newParts: { text: string; isAttr: boolean }[] = [];
    for (const part of parts) {
      if (part.isAttr) { newParts.push(part); continue; }
      let lastIdx = 0;
      const regex = new RegExp(pat.source, pat.flags);
      let m;
      while ((m = regex.exec(part.text)) !== null) {
        if (m.index > lastIdx) newParts.push({ text: part.text.slice(lastIdx, m.index), isAttr: false });
        newParts.push({ text: m[0], isAttr: true });
        lastIdx = m.index + m[0].length;
      }
      if (lastIdx < part.text.length) newParts.push({ text: part.text.slice(lastIdx), isAttr: false });
    }
    parts = newParts;
  }
  return parts.map((p, i) =>
    p.isAttr
      ? <span key={i} className="bg-amber-200 text-amber-900 px-0.5 rounded font-medium">{p.text}</span>
      : <span key={i}>{p.text}</span>
  );
}

// ─── Evidence Panel ─────────────────────────────────────────────────

const EvidencePanel: React.FC<{
  label: string;
  color: 'red' | 'orange';
  evidence: ExpertEvidence;
}> = ({ label, color, evidence }) => {
  const [showCtx, setShowCtx] = useState(true);
  const bg = color === 'red' ? 'bg-red-50' : 'bg-orange-50';
  const border = color === 'red' ? 'border-red-200' : 'border-orange-200';
  const lc = color === 'red' ? 'text-red-600' : 'text-orange-600';
  const sm = evidence.speaker_mode;
  const pl = evidence.plane;

  return (
    <div className={`p-4 ${bg} rounded-xl border ${border}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold ${lc}`}>{label}</span>
          {sm ? (
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${SPEAKER_COLOR[sm] || 'bg-slate-100 text-slate-600 border-slate-200'}`}>
              {SPEAKER_LABEL[sm] || sm}
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-slate-50 text-slate-400 border-slate-200 border-dashed">
              מצב דובר
            </span>
          )}
          {pl ? (
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${PLANE_COLOR[pl] || 'bg-slate-100 text-slate-600 border-slate-200'}`}>
              {PLANE_LABEL[pl] || pl}
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-slate-50 text-slate-400 border-slate-200 border-dashed">
              מישור
            </span>
          )}
          {evidence.negation && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-red-100 text-red-700 border-red-200">שלילה</span>
          )}
          {evidence.modality && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-indigo-100 text-indigo-600 border-indigo-200">{evidence.modality}</span>
          )}
        </div>
        {evidence.doc_id && (
          <span className="text-xs text-slate-400">{evidence.doc_id}</span>
        )}
      </div>

      {/* Context before */}
      {showCtx && (
        evidence.context_before
          ? <p className="text-xs text-slate-400 italic mb-1 leading-relaxed">...{evidence.context_before}</p>
          : <p className="text-xs text-slate-300 italic mb-1 leading-relaxed">&mdash; אין הקשר קודם &mdash;</p>
      )}

      {/* Claim text with attribution highlighting */}
      <p className="text-slate-800 leading-relaxed">{highlightAttribution(evidence.quote)}</p>

      {/* Context after */}
      {showCtx && (
        evidence.context_after
          ? <p className="text-xs text-slate-400 italic mt-1 leading-relaxed">{evidence.context_after}...</p>
          : <p className="text-xs text-slate-300 italic mt-1 leading-relaxed">&mdash; אין הקשר נוסף &mdash;</p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {evidence.entities && evidence.entities.length > 0 && (
            <span className="text-slate-400">ישויות: {evidence.entities.join(', ')}</span>
          )}
          {evidence.time_reference && (
            <span className="text-slate-400">זמן: {evidence.time_reference}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {evidence.section_path && (
            <span className="text-[10px] text-slate-400">{evidence.section_path}</span>
          )}
          {evidence.doc_id && evidence.locator && (
            <button className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1">
              <ExternalLink className="w-3 h-3" />
              מקור
            </button>
          )}
          <button
            onClick={() => setShowCtx(!showCtx)}
            className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1"
          >
            <Eye className="w-3 h-3" />
            {showCtx ? 'הסתר' : 'הקשר'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Decision Page (per pair) ───────────────────────────────────────

const PairDecisionPage: React.FC<{
  pair: PairAnalysisRow;
  index: number;
}> = ({ pair, index }) => {
  const [gatesOpen, setGatesOpen] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const gates = pair.gates;
  const isTrue = pair.is_true_contradiction;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card className={`shadow-md ${isTrue ? 'border-r-4 border-red-500' : 'border-r-4 border-slate-300'}`}>
        <div className="space-y-4">
          {/* Expert Notebook header */}
          <div className={`flex items-center justify-between px-3 py-2 rounded-lg border ${isTrue ? 'bg-gradient-to-l from-red-50 to-orange-50 border-red-100' : 'bg-gradient-to-l from-slate-50 to-indigo-50 border-indigo-100'}`}>
            <div className="flex items-center gap-2">
              <FileText className={`w-4 h-4 ${isTrue ? 'text-red-500' : 'text-indigo-500'}`} />
              <span className={`text-xs font-semibold ${isTrue ? 'text-red-700' : 'text-indigo-700'}`}>
                {isTrue ? 'סתירה אמיתית' : 'ניתוח זוג'} #{index + 1}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${OUTCOME_COLORS[pair.outcome_category] || OUTCOME_COLORS.UNKNOWN}`}>
                {OUTCOME_LABELS[pair.outcome_category] || pair.outcome_category}
              </span>
              <span className="text-[10px] text-slate-400">
                ציון: {(pair.contradiction_score * 100).toFixed(0)}%
              </span>
              <button onClick={() => setExpanded(!expanded)} className="text-slate-400 hover:text-slate-600">
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {expanded && (
            <>
              {/* Claims with context (expanded by default — §10.1) */}
              <div className="space-y-3">
                <EvidencePanel label="טענה א'" color="red" evidence={pair.claim_a} />
                <EvidencePanel label="טענה ב'" color="orange" evidence={pair.claim_b} />
              </div>

              {/* Gate checks (§10.3) */}
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <button
                  onClick={() => setGatesOpen(!gatesOpen)}
                  className="w-full flex items-center justify-between px-4 py-2 bg-slate-50 hover:bg-slate-100 transition-colors"
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <Shield className="w-4 h-4" />
                    <span>בדיקות שערים</span>
                  </div>
                  {gatesOpen ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                </button>
                {gatesOpen && (
                  <div className="p-3 grid grid-cols-2 gap-2">
                    {Object.entries(gates).map(([key, val]) => {
                      if (typeof val !== 'boolean' && val !== null) return null;
                      const passed = val === true;
                      const failed = val === false;
                      return (
                        <div key={key} className="flex items-center gap-2 text-xs">
                          {passed ? (
                            <ShieldCheck className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                          ) : failed ? (
                            <ShieldX className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
                          ) : (
                            <Shield className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
                          )}
                          <span className={passed ? 'text-green-700' : failed ? 'text-red-700' : 'text-slate-500'}>
                            {GATE_LABELS[key] || key}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Reconciliation attempt (§10.4) */}
              <div className="p-3 bg-indigo-50 rounded-xl border border-indigo-100">
                <div className="text-xs text-indigo-600 font-medium mb-1 flex items-center gap-1">
                  <Search className="w-3 h-3" />
                  ניסיון יישוב
                </div>
                {pair.reconciliation_attempt ? (
                  <p className="text-sm text-slate-700">{pair.reconciliation_attempt}</p>
                ) : (
                  <p className="text-sm text-slate-400 italic">לא בוצע ניסיון יישוב</p>
                )}
                {pair.rationale && (
                  <p className="text-sm text-indigo-800 mt-1">{pair.rationale}</p>
                )}
                {pair.deciding_fields.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {pair.deciding_fields.map((f) => (
                      <span key={f} className="text-[10px] px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded">{f}</span>
                    ))}
                  </div>
                )}
              </div>

              {/* Final decision (§10.5) */}
              <div className="p-4 bg-slate-50 rounded-xl">
                <div className="flex items-center gap-2 mb-1">
                  <Lock className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-xs text-slate-500 font-medium">החלטה סופית (נעולה לשערים)</span>
                </div>
                <p className={`font-medium ${isTrue ? 'text-red-700' : 'text-slate-600'}`}>
                  {OUTCOME_LABELS[pair.outcome_category] || pair.outcome_category}
                </p>
              </div>

              {/* Hard UI stop: "Mark as contradiction" button (§10.6) */}
              <div className="flex items-center justify-between">
                <button
                  disabled={!isTrue}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                    isTrue
                      ? 'bg-red-600 text-white hover:bg-red-700'
                      : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                  }`}
                  title={!isTrue ? `חסום: ${pair.blocked_reasons.join(', ')}` : 'סמן כסתירה'}
                >
                  <AlertTriangle className="w-4 h-4" />
                  סמן כסתירה
                </button>
                {!isTrue && pair.blocked_reasons.length > 0 && (
                  <span className="text-xs text-slate-400 flex items-center gap-1">
                    <Lock className="w-3 h-3" />
                    {pair.blocked_reasons.map((r) => {
                      if (r.startsWith('outcome=')) return OUTCOME_LABELS[r.replace('outcome=', '')] || r;
                      if (r.includes('PARTY_CLAIM')) return 'טענת צד';
                      if (r.includes('missing_context')) return 'הקשר חסר';
                      return r;
                    }).join(' | ')}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      </Card>
    </motion.div>
  );
};

// ─── Summary Dashboard ──────────────────────────────────────────────

const SummaryDashboard: React.FC<{ summary: ExpertSummaryReport }> = ({ summary }) => {
  const total = summary.total_pairs_analyzed;
  const trueCount = summary.true_contradiction_count;

  return (
    <Card className="shadow-md">
      <div className="space-y-4">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-gradient-to-l from-indigo-50 to-purple-50 rounded-lg border border-indigo-100">
          <BarChart3 className="w-4 h-4 text-indigo-500" />
          <span className="text-xs font-semibold text-indigo-700">סיכום ניתוח מומחה</span>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-4 gap-3">
          <div className="p-3 bg-slate-50 rounded-xl text-center">
            <div className="text-2xl font-bold text-slate-800">{total}</div>
            <div className="text-xs text-slate-500">זוגות נותחו</div>
          </div>
          <div className="p-3 bg-red-50 rounded-xl text-center">
            <div className="text-2xl font-bold text-red-700">{trueCount}</div>
            <div className="text-xs text-red-600">סתירות אמיתיות</div>
          </div>
          <div className="p-3 bg-yellow-50 rounded-xl text-center">
            <div className="text-2xl font-bold text-yellow-700">{total - trueCount}</div>
            <div className="text-xs text-yellow-600">לא-סתירות (רעש)</div>
          </div>
          <div className="p-3 bg-indigo-50 rounded-xl text-center">
            <div className="text-2xl font-bold text-indigo-700">
              {total > 0 ? `${(summary.noise_to_signal_ratio * 100).toFixed(0)}%` : '0%'}
            </div>
            <div className="text-xs text-indigo-600">יחס רעש/אות</div>
          </div>
        </div>

        {/* Distribution bar */}
        {total > 0 && (
          <div>
            <div className="text-xs text-slate-500 mb-2">התפלגות לפי קטגוריה</div>
            <div className="flex rounded-full overflow-hidden h-4">
              {Object.entries(summary.distribution).map(([cat, count]) => {
                const pct = (count / total) * 100;
                const color = cat === 'TRUE_CONTRADICTION' ? 'bg-red-500' :
                  cat === 'APPARENT_TENSION_RESOLVABLE' ? 'bg-yellow-400' :
                  cat === 'DISAGREEMENT_BETWEEN_PARTIES' ? 'bg-orange-400' :
                  cat === 'ROLE_OR_ATTRIBUTION_MISMATCH' ? 'bg-purple-400' :
                  cat === 'PLANE_MISMATCH' ? 'bg-blue-400' :
                  cat === 'TIME_OR_STAGE_SHIFT' ? 'bg-teal-400' :
                  'bg-slate-300';
                return pct > 0 ? (
                  <div
                    key={cat}
                    className={`${color} transition-all`}
                    style={{ width: `${pct}%` }}
                    title={`${OUTCOME_LABELS[cat] || cat}: ${count}`}
                  />
                ) : null;
              })}
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {Object.entries(summary.distribution).map(([cat, count]) => (
                <span key={cat} className={`text-[10px] px-1.5 py-0.5 rounded border ${OUTCOME_COLORS[cat] || ''}`}>
                  {OUTCOME_LABELS[cat] || cat}: {count}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Top findings */}
        {summary.top_findings.length > 0 && (
          <div>
            <div className="text-xs text-slate-500 mb-1">ממצאים עיקריים</div>
            <ul className="space-y-1">
              {summary.top_findings.map((f, i) => (
                <li key={i} className="text-sm text-red-700 flex items-start gap-2">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
};

// ─── Main Page ──────────────────────────────────────────────────────

export const ExpertNotebookPage: React.FC = () => {
  const [text, setText] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [notebook, setNotebook] = useState<ExpertNotebookPayload | null>(null);
  const [error, setError] = useState('');
  const [filterOutcome, setFilterOutcome] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const handleAnalyze = async () => {
    if (!text.trim()) return;
    setIsAnalyzing(true);
    setError('');
    setNotebook(null);

    try {
      const result: AnalysisResponse = await analysisApi.analyzeText({ text });
      if (result.expert_notebook) {
        setNotebook(result.expert_notebook);
      } else {
        setError('הניתוח לא החזיר נתוני מחברת מומחה');
      }
    } catch (e) {
      setError(handleApiError(e));
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Filter pairs
  const filteredPairs = notebook?.pair_analysis.filter((p) => {
    if (filterOutcome && p.outcome_category !== filterOutcome) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        p.claim_a.quote.toLowerCase().includes(q) ||
        p.claim_b.quote.toLowerCase().includes(q) ||
        (p.claim_a.doc_id || '').toLowerCase().includes(q) ||
        (p.claim_b.doc_id || '').toLowerCase().includes(q) ||
        (p.claim_a.entities || []).some(e => e.toLowerCase().includes(q)) ||
        (p.claim_b.entities || []).some(e => e.toLowerCase().includes(q))
      );
    }
    return true;
  }) || [];

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FileText className="w-6 h-6 text-indigo-500" />
            מחברת מומחה לניתוח סתירות
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            ניתוח מלא עם שערים, יישוב, והחלטות נעולות — Cursor 5.2
          </p>
        </div>
      </div>

      {/* Text input */}
      <Card>
        <div className="space-y-4">
          <textarea
            dir="rtl"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="הכנס טקסט משפטי לניתוח מומחה..."
            className="w-full h-40 p-4 border border-slate-200 rounded-xl resize-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 outline-none text-slate-800"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">{text.length} תווים</span>
            <Button
              onClick={handleAnalyze}
              disabled={!text.trim() || isAnalyzing}
            >
              {isAnalyzing ? <Spinner size="sm" /> : <Search className="w-4 h-4" />}
              {isAnalyzing ? 'מנתח...' : 'הפעל ניתוח מומחה'}
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {notebook && (
        <div className="space-y-6">
          {/* Summary dashboard */}
          <SummaryDashboard summary={notebook.summary_report} />

          {/* Filters */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <Filter className="w-4 h-4" />
              <span>סינון:</span>
            </div>
            <button
              onClick={() => setFilterOutcome(null)}
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                !filterOutcome ? 'bg-indigo-100 text-indigo-700 border-indigo-200' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
              }`}
            >
              הכל ({notebook.pair_analysis.length})
            </button>
            {Object.entries(notebook.summary_report.distribution).map(([cat, count]) => (
              <button
                key={cat}
                onClick={() => setFilterOutcome(filterOutcome === cat ? null : cat)}
                className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                  filterOutcome === cat ? 'bg-indigo-100 text-indigo-700 border-indigo-200' : `border ${OUTCOME_COLORS[cat] || 'bg-white text-slate-600 border-slate-200'} hover:opacity-80`
                }`}
              >
                {OUTCOME_LABELS[cat] || cat} ({count})
              </button>
            ))}

            {/* Search */}
            <div className="flex-1 min-w-[200px]">
              <input
                dir="rtl"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="חיפוש לפי ישות / מסמך..."
                className="w-full px-3 py-1 text-xs border border-slate-200 rounded-full focus:ring-2 focus:ring-indigo-200 outline-none"
              />
            </div>
          </div>

          {/* Pair list */}
          <div className="space-y-4">
            <AnimatePresence>
              {filteredPairs.map((pair, i) => (
                <PairDecisionPage key={pair.pair_id} pair={pair} index={i} />
              ))}
            </AnimatePresence>
            {filteredPairs.length === 0 && (
              <EmptyState
                icon={<FileText className="w-16 h-16" />}
                title="לא נמצאו זוגות"
                description={filterOutcome ? 'נסה לשנות את הסינון' : 'לא נמצאו זוגות לניתוח'}
              />
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!notebook && !isAnalyzing && !error && (
        <EmptyState
          icon={<FileText className="w-16 h-16" />}
          title="מחברת מומחה לניתוח סתירות"
          description="הכנס טקסט משפטי ולחץ 'הפעל ניתוח מומחה' כדי לקבל ניתוח מלא עם שערים, יישוב, והחלטות."
        />
      )}
    </div>
  );
};
