import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  AlertTriangle,
  CheckCircle,
  Lightbulb,
  Copy,
  FileText,
  ArrowDown,
  Sparkles,
  MessageSquare,
  Shield,
  ShieldCheck,
  ShieldX,
  Lock,
  Eye,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { analysisApi, handleApiError } from '../api';
import { Card, Button, Badge, Progress, Spinner, EmptyState } from '../components/ui';
import type { AnalysisResponse, Contradiction, ClaimEvidence, CrossExamQuestion, CrossExamQuestionsOutput } from '../types';

// Helper to flatten cross-exam questions from nested structure
const flattenCrossExamQuestions = (
  questions: CrossExamQuestionsOutput[] | CrossExamQuestion[] | undefined
): CrossExamQuestion[] => {
  if (!questions || questions.length === 0) return [];

  // Check if it's already a flat array of questions
  const first = questions[0];
  if ('question' in first && typeof first.question === 'string') {
    // Already flat
    return questions as CrossExamQuestion[];
  }

  // It's nested - flatten
  return (questions as CrossExamQuestionsOutput[]).flatMap(
    (set) => set.questions || []
  );
};

export const AnalyzePage: React.FC = () => {
  const [text, setText] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'claims' | 'contradictions' | 'questions'>('contradictions');

  const handleAnalyze = async () => {
    if (!text.trim()) {
      setError('יש להזין טקסט לניתוח');
      return;
    }

    setIsAnalyzing(true);
    setError('');
    setProgress(0);
    setResult(null);

    // Simulate progress
    const progressInterval = setInterval(() => {
      setProgress((prev) => Math.min(prev + 5, 90));
    }, 200);

    try {
      const response = await analysisApi.analyzeText({
        text,
        source_name: sourceName || undefined,
      });

      clearInterval(progressInterval);
      setProgress(100);
      setResult(response);
    } catch (err) {
      clearInterval(progressInterval);
      setError(handleApiError(err));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const copyToClipboard = (textToCopy: string) => {
    navigator.clipboard.writeText(textToCopy);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">ניתוח טקסט</h1>
        <p className="text-slate-500 mt-1">
          הדביקו טקסט מעדות, מסמך או כל מקור אחר וזהו סתירות פוטנציאליות
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input Section */}
        <div className="space-y-4">
          <Card>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  שם המקור (אופציונלי)
                </label>
                <input
                  type="text"
                  value={sourceName}
                  onChange={(e) => setSourceName(e.target.value)}
                  placeholder="לדוגמה: עדות יוסי כהן"
                  className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  טקסט לניתוח
                </label>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="הדביקו כאן את הטקסט לניתוח...

לדוגמה:
בתאריך 15.3.2023 הייתי בבית בשעה 20:00. ראיתי את הנתבע מגיע לביתי בשעה 19:30. יצאתי מהעבודה בשעה 21:00 באותו יום."
                  rows={12}
                  className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none resize-none"
                />
                <div className="flex justify-between mt-2 text-sm text-slate-500">
                  <span>{text.length} תווים</span>
                  <span>{text.split(/\s+/).filter(Boolean).length} מילים</span>
                </div>
              </div>

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm"
                >
                  {error}
                </motion.div>
              )}

              {isAnalyzing && (
                <div className="space-y-3">
                  <Progress value={progress} showLabel label="מנתח טקסט..." />
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Sparkles className="w-4 h-4 animate-pulse text-primary-500" />
                    <span>מחלץ טענות ומזהה סתירות...</span>
                  </div>
                </div>
              )}

              <Button
                onClick={handleAnalyze}
                className="w-full"
                size="lg"
                isLoading={isAnalyzing}
                leftIcon={<Search className="w-5 h-5" />}
              >
                נתח טקסט
              </Button>
            </div>
          </Card>

          {/* Tips */}
          <Card className="bg-primary-50 border-primary-100">
            <div className="flex gap-3">
              <Lightbulb className="w-5 h-5 text-primary-600 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-semibold text-primary-900 mb-2">טיפים לתוצאות טובות יותר</h3>
                <ul className="text-sm text-primary-700 space-y-1">
                  <li>• הכניסו טקסט מלא עם פרטים ספציפיים</li>
                  <li>• ציינו תאריכים, שעות ומספרים במדויק</li>
                  <li>• כללו מספר פסקאות או עדויות שונות</li>
                  <li>• השתמשו בעברית תקנית</li>
                </ul>
              </div>
            </div>
          </Card>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {!result && !isAnalyzing && (
            <Card className="h-full flex items-center justify-center min-h-[400px]">
              <EmptyState
                icon={<FileText className="w-16 h-16" />}
                title="מוכן לניתוח"
                description="הזינו טקסט ולחצו על 'נתח טקסט' כדי לזהות סתירות"
              />
            </Card>
          )}

          {isAnalyzing && (
            <Card className="h-full flex items-center justify-center min-h-[400px]">
              <div className="text-center">
                <Spinner size="lg" className="mx-auto mb-4" />
                <p className="text-lg font-medium text-slate-700">מנתח את הטקסט...</p>
                <p className="text-sm text-slate-500 mt-2">זה עשוי לקחת מספר שניות</p>
              </div>
            </Card>
          )}

          {result && !isAnalyzing && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              {/* Summary */}
              {(() => {
                const flatQuestions = flattenCrossExamQuestions(result.cross_exam_questions);
                return (
                  <>
                    <Card className="bg-gradient-to-br from-slate-50 to-slate-100">
                      <div className="space-y-4">
                        <div className="grid grid-cols-3 gap-4 text-center">
                          <div>
                            <div className="text-3xl font-bold text-slate-900">
                              {result.claims?.length || 0}
                            </div>
                            <div className="text-sm text-slate-500">טענות זוהו</div>
                          </div>
                          <div>
                            <div className="text-3xl font-bold text-warning-600">
                              {result.contradictions?.length || 0}
                            </div>
                            <div className="text-sm text-slate-500">סתירות נמצאו</div>
                          </div>
                          <div>
                            <div className="text-3xl font-bold text-primary-600">
                              {flatQuestions.length}
                            </div>
                            <div className="text-sm text-slate-500">שאלות הומלצו</div>
                          </div>
                        </div>
                        {/* Severity mini-bar */}
                        {result.contradictions && result.contradictions.length > 0 && (() => {
                          const sevCounts: Record<string, number> = {};
                          const catCounts: Record<string, number> = {};
                          result.contradictions.forEach((c) => {
                            const s = c.severity || 'medium';
                            sevCounts[s] = (sevCounts[s] || 0) + 1;
                            const cat = c.category || 'unclassified';
                            catCounts[cat] = (catCounts[cat] || 0) + 1;
                          });
                          const total = result.contradictions.length;
                          const order = ['critical', 'high', 'medium', 'low'];
                          const colors: Record<string, string> = { critical: 'bg-red-600', high: 'bg-red-400', medium: 'bg-orange-400', low: 'bg-yellow-400' };
                          const labels: Record<string, string> = { critical: 'קריטי', high: 'גבוה', medium: 'בינוני', low: 'נמוך' };
                          const catLabels: Record<string, string> = {
                            'HARD_CONTRADICTION': 'סתירה מוכרחת',
                            'TRUE_CONTRADICTION': 'סתירה אמיתית',
                            'APPARENT_TENSION_RESOLVABLE': 'מתח לכאורה',
                            'DISAGREEMENT_BETWEEN_PARTIES': 'מחלוקת בין צדדים',
                            'ROLE_OR_ATTRIBUTION_MISMATCH': 'אי\u2011התאמה בייחוס/תפקיד',
                            'NARRATIVE_AMBIGUITY': 'עמימות נרטיבית',
                            'LOGICAL_INCONSISTENCY': 'אי\u2011עקביות',
                            'RHETORICAL_SHIFT': 'שינוי רטורי',
                            'PLANE_MISMATCH': 'חוסר התאמה במישור',
                            'TIME_OR_STAGE_SHIFT': 'שינוי זמן/שלב',
                            'AMBIGUITY_OR_VAGUENESS': 'עמימות',
                            'INSUFFICIENT_CONTEXT': 'הקשר חסר',
                            'DUPLICATE_OR_RESTATEMENT': 'כפילות',
                            'unclassified': 'לא מסווג',
                          };
                          const catColors: Record<string, string> = {
                            'HARD_CONTRADICTION': 'bg-red-500', 'TRUE_CONTRADICTION': 'bg-red-600',
                            'APPARENT_TENSION_RESOLVABLE': 'bg-amber-400', 'DISAGREEMENT_BETWEEN_PARTIES': 'bg-indigo-400',
                            'ROLE_OR_ATTRIBUTION_MISMATCH': 'bg-violet-400', 'INSUFFICIENT_CONTEXT': 'bg-orange-300',
                            'NARRATIVE_AMBIGUITY': 'bg-orange-400', 'LOGICAL_INCONSISTENCY': 'bg-blue-400',
                            'RHETORICAL_SHIFT': 'bg-slate-400', 'PLANE_MISMATCH': 'bg-purple-400',
                            'TIME_OR_STAGE_SHIFT': 'bg-cyan-400', 'AMBIGUITY_OR_VAGUENESS': 'bg-yellow-400',
                            'DUPLICATE_OR_RESTATEMENT': 'bg-slate-300', 'unclassified': 'bg-slate-300',
                          };
                          const hasMultipleCategories = Object.keys(catCounts).length > 1 || (Object.keys(catCounts).length === 1 && !catCounts['unclassified']);
                          return (
                            <div className="space-y-3">
                              {/* Severity bar */}
                              <div className="space-y-1">
                                <div className="text-xs text-slate-500 font-medium">חומרה</div>
                                <div className="flex h-3 rounded-full overflow-hidden bg-slate-200">
                                  {order.map((s) => {
                                    const count = sevCounts[s] || 0;
                                    if (count === 0) return null;
                                    return <div key={s} className={`${colors[s]}`} style={{ width: `${(count / total) * 100}%` }} title={`${labels[s]}: ${count}`} />;
                                  })}
                                </div>
                                <div className="flex flex-wrap gap-3 text-xs text-slate-600">
                                  {order.map((s) => {
                                    const count = sevCounts[s] || 0;
                                    if (count === 0) return null;
                                    return (
                                      <div key={s} className="flex items-center gap-1">
                                        <div className={`w-2 h-2 rounded-full ${colors[s]}`} />
                                        <span>{labels[s]}: {count}</span>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                              {/* Category bar */}
                              {hasMultipleCategories && (
                                <div className="space-y-1">
                                  <div className="text-xs text-slate-500 font-medium">קטגוריה</div>
                                  <div className="flex h-3 rounded-full overflow-hidden bg-slate-200">
                                    {Object.entries(catCounts).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
                                      <div key={cat} className={`${catColors[cat] || 'bg-slate-400'}`} style={{ width: `${(count / total) * 100}%` }} title={`${catLabels[cat] || cat}: ${count}`} />
                                    ))}
                                  </div>
                                  <div className="flex flex-wrap gap-3 text-xs text-slate-600">
                                    {Object.entries(catCounts).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
                                      <div key={cat} className="flex items-center gap-1">
                                        <div className={`w-2 h-2 rounded-full ${catColors[cat] || 'bg-slate-400'}`} />
                                        <span>{catLabels[cat] || cat}: {count}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                        {/* Duration */}
                        {result.metadata?.duration_ms && (
                          <div className="text-xs text-slate-400 text-center">
                            ניתוח הושלם ב-{Math.round(result.metadata.duration_ms)}ms
                          </div>
                        )}
                      </div>
                    </Card>

                    {/* Tabs */}
                    <div className="flex gap-2">
                      <Button
                        variant={activeTab === 'claims' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setActiveTab('claims')}
                        leftIcon={<FileText className="w-4 h-4" />}
                      >
                        טענות ({result.claims?.length || 0})
                      </Button>
                      <Button
                        variant={activeTab === 'contradictions' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setActiveTab('contradictions')}
                        leftIcon={<AlertTriangle className="w-4 h-4" />}
                      >
                        סתירות ({result.contradictions?.length || 0})
                      </Button>
                      <Button
                        variant={activeTab === 'questions' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setActiveTab('questions')}
                        leftIcon={<MessageSquare className="w-4 h-4" />}
                      >
                        שאלות ({flatQuestions.length})
                      </Button>
                    </div>
                  </>
                );
              })()}

              {/* Content */}
              <AnimatePresence mode="wait">
                {activeTab === 'claims' && (
                  <motion.div
                    key="claims"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-3"
                  >
                    {result.claims?.length === 0 ? (
                      <Card>
                        <div className="text-center py-8">
                          <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                          <p className="text-lg font-medium text-slate-700">
                            לא זוהו טענות
                          </p>
                          <p className="text-sm text-slate-500 mt-2">
                            נסה להזין טקסט מפורט יותר
                          </p>
                        </div>
                      </Card>
                    ) : (
                      result.claims?.map((claim, index) => (
                        <motion.div
                          key={claim.id || index}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: index * 0.05 }}
                        >
                          <Card className="border-r-4 border-primary-400">
                            <div className="flex items-start gap-3">
                              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-600 font-bold text-sm flex-shrink-0">
                                {index + 1}
                              </div>
                              <div className="flex-1">
                                <p className="text-slate-900">{claim.text}</p>
                                <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                                  {claim.source_name && (
                                    <span>מקור: {claim.source_name}</span>
                                  )}
                                  {claim.speaker && (
                                    <span>דובר: {claim.speaker}</span>
                                  )}
                                  {claim.category && (
                                    <Badge variant="neutral" size="sm">{claim.category}</Badge>
                                  )}
                                </div>
                              </div>
                            </div>
                          </Card>
                        </motion.div>
                      ))
                    )}
                  </motion.div>
                )}

                {activeTab === 'contradictions' && (
                  <motion.div
                    key="contradictions"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-4"
                  >
                    {result.contradictions?.length === 0 ? (
                      <Card>
                        <div className="text-center py-8">
                          <CheckCircle className="w-12 h-12 text-success-500 mx-auto mb-4" />
                          <p className="text-lg font-medium text-slate-700">
                            לא נמצאו סתירות
                          </p>
                          <p className="text-sm text-slate-500 mt-2">
                            הטקסט נראה עקבי ואין סתירות ברורות
                          </p>
                        </div>
                      </Card>
                    ) : (
                      result.contradictions?.map((contradiction, index) => (
                        <ContradictionCard
                          key={contradiction.id || index}
                          contradiction={contradiction}
                          index={index}
                        />
                      ))
                    )}
                  </motion.div>
                )}

                {activeTab === 'questions' && (
                  <motion.div
                    key="questions"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-4"
                  >
                    {(() => {
                      const flatQuestions = flattenCrossExamQuestions(result.cross_exam_questions);
                      if (flatQuestions.length === 0) {
                        return (
                          <Card>
                            <div className="text-center py-8">
                              <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                              <p className="text-lg font-medium text-slate-700">
                                אין שאלות מומלצות
                              </p>
                              <p className="text-sm text-slate-500 mt-2">
                                שאלות נוצרות כאשר מזוהות סתירות
                              </p>
                            </div>
                          </Card>
                        );
                      }
                      return flatQuestions.map((question, index) => (
                        <QuestionCard
                          key={question.id || index}
                          question={question}
                          index={index}
                          onCopy={copyToClipboard}
                        />
                      ));
                    })()}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};

// Contradiction Card Component
// --- Attribution phrase highlighting (Cursor 5.2 §10h) ---
const ATTRIBUTION_PATTERNS = [
  /לטענת[ו]?/g, /נטען/g, /לכאורה/g, /ייתכן/g, /סביר להניח/g,
  /נראה כי/g, /ככל הנראה/g, /כנטען/g, /לדבריו/g, /לדבריה/g,
  /טוען/g, /טוענת/g, /הנתבע טען/g, /התובע טען/g,
];

function highlightAttribution(text: string): React.ReactNode[] {
  if (!text) return [text];
  const parts: React.ReactNode[] = [];
  let lastIdx = 0;
  const matches: { start: number; end: number }[] = [];
  for (const pat of ATTRIBUTION_PATTERNS) {
    pat.lastIndex = 0;
    let m;
    while ((m = pat.exec(text)) !== null) {
      matches.push({ start: m.index, end: m.index + m[0].length });
    }
  }
  matches.sort((a, b) => a.start - b.start);
  // Merge overlapping
  const merged: { start: number; end: number }[] = [];
  for (const m of matches) {
    if (merged.length && m.start <= merged[merged.length - 1].end) {
      merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, m.end);
    } else {
      merged.push({ ...m });
    }
  }
  for (const m of merged) {
    if (m.start > lastIdx) parts.push(text.slice(lastIdx, m.start));
    parts.push(
      <mark key={m.start} className="bg-amber-200 text-amber-900 px-0.5 rounded" title="ביטוי ייחוס">
        {text.slice(m.start, m.end)}
      </mark>
    );
    lastIdx = m.end;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return parts;
}

// --- Speaker mode / plane badge helpers ---
const speakerModeLabel: Record<string, string> = {
  finding: 'קביעה שיפוטית',
  party_claim: 'טענת צד',
  quote: 'ציטוט',
  law_citation: 'אזכור חוק',
  opinion: 'דעה / הערכה',
};
const planeLabel: Record<string, string> = {
  FACT: 'עובדה',
  LAW: 'חוק',
  OPINION: 'דעה',
  PROCEDURAL: 'פרוצדורלי',
};
const speakerModeBadgeColor: Record<string, string> = {
  finding: 'bg-blue-100 text-blue-800 border-blue-200',
  party_claim: 'bg-orange-100 text-orange-800 border-orange-200',
  quote: 'bg-purple-100 text-purple-800 border-purple-200',
  law_citation: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  opinion: 'bg-pink-100 text-pink-800 border-pink-200',
};
const planeBadgeColor: Record<string, string> = {
  FACT: 'bg-sky-100 text-sky-800 border-sky-200',
  LAW: 'bg-teal-100 text-teal-800 border-teal-200',
  OPINION: 'bg-pink-100 text-pink-800 border-pink-200',
  PROCEDURAL: 'bg-slate-100 text-slate-700 border-slate-200',
};

// --- Gate labels ---
const gateLabels: Record<string, string> = {
  claim_a_complete: 'שלמות טענה א׳',
  claim_b_complete: 'שלמות טענה ב׳',
  time_match: 'תאימות זמן',
  scope_match: 'תאימות היקף',
  quantifier_match: 'כמת (quantifier)',
  modality_match: 'מודאליות',
  speaker_mode_ok: 'מצב דובר',
  plane_match: 'מישור',
};

// --- Claim panel with context + badges ---
const ClaimPanel: React.FC<{
  label: string;
  color: string;
  claim?: { text?: string; source_name?: string; speaker?: string };
  evidence?: ClaimEvidence;
}> = ({ label, color, claim, evidence }) => {
  const [showContext, setShowContext] = useState(true);
  const text = evidence?.quote || claim?.text || 'לא זמין';
  const sm = evidence?.speaker_mode;
  const pl = evidence?.plane;
  const ctxBefore = evidence?.context_before;
  const ctxAfter = evidence?.context_after;

  const borderColor = color === 'red' ? 'border-red-200' : 'border-orange-200';
  const bgColor = color === 'red' ? 'bg-red-50' : 'bg-orange-50';
  const labelColor = color === 'red' ? 'text-red-600' : 'text-orange-600';

  return (
    <div className={`p-4 ${bgColor} rounded-xl border ${borderColor}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold ${labelColor}`}>{label}</span>
          {sm ? (
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${speakerModeBadgeColor[sm] || 'bg-slate-100 text-slate-600 border-slate-200'}`}>
              {speakerModeLabel[sm] || sm}
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-slate-50 text-slate-400 border-slate-200 border-dashed">
              מצב דובר
            </span>
          )}
          {pl ? (
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${planeBadgeColor[pl] || 'bg-slate-100 text-slate-600 border-slate-200'}`}>
              {planeLabel[pl] || pl}
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-slate-50 text-slate-400 border-slate-200 border-dashed">
              מישור
            </span>
          )}
          {evidence?.negation && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-red-100 text-red-700 border-red-200">שלילה</span>
          )}
        </div>
        {claim?.source_name && (
          <span className="text-xs text-slate-400">{claim.source_name}</span>
        )}
      </div>

      {/* Context before */}
      {showContext && (
        ctxBefore
          ? <p className="text-xs text-slate-400 italic mb-1 leading-relaxed">...{ctxBefore}</p>
          : <p className="text-xs text-slate-300 italic mb-1 leading-relaxed">— אין הקשר קודם —</p>
      )}

      {/* Claim text with attribution highlighting */}
      <p className="text-slate-800 leading-relaxed">{highlightAttribution(text)}</p>

      {/* Context after */}
      {showContext && (
        ctxAfter
          ? <p className="text-xs text-slate-400 italic mt-1 leading-relaxed">{ctxAfter}...</p>
          : <p className="text-xs text-slate-300 italic mt-1 leading-relaxed">— אין הקשר נוסף —</p>
      )}

      {/* Footer: speaker, entities, toggle */}
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {claim?.speaker && <span>דובר: {claim.speaker}</span>}
          {evidence?.entities && evidence.entities.length > 0 && (
            <span className="text-slate-400">ישויות: {evidence.entities.join(', ')}</span>
          )}
        </div>
        <button
          onClick={() => setShowContext(!showContext)}
          className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1"
        >
          <Eye className="w-3 h-3" />
          {showContext ? 'הסתר הקשר' : 'הצג הקשר'}
        </button>
      </div>
    </div>
  );
};

const ContradictionCard: React.FC<{ contradiction: Contradiction; index: number }> = ({
  contradiction,
  index,
}) => {
  const [gatesOpen, setGatesOpen] = useState(false);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
      case 'high':
        return 'danger';
      case 'medium':
        return 'warning';
      default:
        return 'neutral';
    }
  };

  const getSeverityLabel = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'קריטי';
      case 'high':
        return 'גבוה';
      case 'medium':
        return 'בינוני';
      case 'low':
        return 'נמוך';
      default:
        return severity;
    }
  };

  const getTypeLabel = (type: string) => {
    const types: Record<string, string> = {
      'TEMPORAL_DATE': 'סתירה בתאריכים',
      'QUANTITATIVE_AMOUNT': 'סתירה בכמויות/סכומים',
      'ACTOR_ATTRIBUTION': 'סתירה בזיהוי מבצע הפעולה',
      'PRESENCE_PARTICIPATION': 'סתירה בנוכחות/השתתפות',
      'DOCUMENT_EXISTENCE': 'סתירה בקיום מסמך',
      'IDENTITY_BASIC': 'סתירה בזיהוי/זהות',
    };
    return types[type] || type;
  };

  // Generate explanation if not provided
  const getExplanation = () => {
    if (contradiction.explanation_he) return contradiction.explanation_he;
    if (contradiction.explanation) return contradiction.explanation;
    const key = contradiction.contradiction_type || contradiction.type || '';
    const explanations: Record<string, string> = {
      'TEMPORAL_DATE': 'התאריכים בשתי הטענות אינם תואמים. יש לברר איזה תאריך הוא הנכון.',
      'QUANTITATIVE_AMOUNT': 'הכמויות או הסכומים המצוינים בשתי הטענות שונים זה מזה.',
      'ACTOR_ATTRIBUTION': 'יש אי-התאמה לגבי מי ביצע את הפעולה המתוארת.',
      'PRESENCE_PARTICIPATION': 'הטענות סותרות זו את זו לגבי נוכחות או השתתפות במאורע.',
      'DOCUMENT_EXISTENCE': 'יש סתירה לגבי קיומו או אי-קיומו של מסמך.',
      'IDENTITY_BASIC': 'פרטי הזיהוי בשתי הטענות אינם תואמים.',
    };
    return explanations[key] || 'שתי הטענות מכילות מידע סותר שדורש בירור נוסף.';
  };

  const getCategoryLabel = (cat?: string) => {
    const labels: Record<string, string> = {
      'HARD_CONTRADICTION': 'סתירה מוכרחת',
      'NARRATIVE_AMBIGUITY': 'עמימות נרטיבית',
      'LOGICAL_INCONSISTENCY': 'אי\u2011עקביות לוגית',
      'RHETORICAL_SHIFT': 'שינוי רטורי',
      'TRUE_CONTRADICTION': 'סתירה אמיתית',
      'APPARENT_TENSION_RESOLVABLE': 'מתח לכאורה — ניתן ליישוב',
      'DISAGREEMENT_BETWEEN_PARTIES': 'מחלוקת בין צדדים',
      'ROLE_OR_ATTRIBUTION_MISMATCH': 'אי\u2011התאמה בייחוס/תפקיד',
      'PLANE_MISMATCH': 'חוסר התאמה במישור',
      'TIME_OR_STAGE_SHIFT': 'שינוי זמן או שלב',
      'AMBIGUITY_OR_VAGUENESS': 'עמימות או אי\u2011בהירות',
      'INSUFFICIENT_CONTEXT': 'הקשר חסר',
      'DUPLICATE_OR_RESTATEMENT': 'כפילות או ניסוח מחדש',
    };
    return cat ? labels[cat] || cat : null;
  };
  const getCategoryColor = (cat?: string) => {
    switch (cat) {
      case 'HARD_CONTRADICTION':
      case 'TRUE_CONTRADICTION': return 'danger';
      case 'NARRATIVE_AMBIGUITY':
      case 'APPARENT_TENSION_RESOLVABLE': return 'warning';
      case 'LOGICAL_INCONSISTENCY':
      case 'DISAGREEMENT_BETWEEN_PARTIES': return 'accent';
      case 'ROLE_OR_ATTRIBUTION_MISMATCH': return 'accent';
      case 'RHETORICAL_SHIFT':
      case 'PLANE_MISMATCH':
      case 'TIME_OR_STAGE_SHIFT': return 'neutral';
      case 'AMBIGUITY_OR_VAGUENESS': return 'warning';
      case 'INSUFFICIENT_CONTEXT': return 'warning';
      case 'DUPLICATE_OR_RESTATEMENT': return 'neutral';
      default: return 'neutral';
    }
  };

  const severity = contradiction.severity || 'medium';
  const contradictionType = contradiction.contradiction_type || contradiction.type || 'unknown';
  const gates = contradiction.gate_results;
  const ev1 = contradiction.claim1;
  const ev2 = contradiction.claim2;

  // Hard UI stops (§10f): disable "mark as contradiction" when conditions are not met
  const hasContext = !!(ev1?.context_before || ev1?.context_after || ev2?.context_before || ev2?.context_after);
  const hasPartyClaimBlock = ev1?.speaker_mode === 'party_claim' || ev2?.speaker_mode === 'party_claim';
  const hasPlaneMismatch = ev1?.plane && ev2?.plane && ev1.plane !== ev2.plane;
  const reconciliationSucceeded = contradiction.reconciler_outcome
    && contradiction.reconciler_outcome !== 'TRUE_CONTRADICTION'
    && contradiction.reconciler_outcome !== 'APPARENT_TENSION_RESOLVABLE';
  const markDisabled = !hasContext || hasPartyClaimBlock || hasPlaneMismatch || !!reconciliationSucceeded;

  const disableReasons: string[] = [];
  if (!hasContext) disableReasons.push('הקשר חסר');
  if (hasPartyClaimBlock) disableReasons.push('טענת צד');
  if (hasPlaneMismatch) disableReasons.push('חוסר התאמה במישור');
  if (reconciliationSucceeded) disableReasons.push('יישוב הצליח');

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
    >
      <Card className="border-r-4 border-warning-500 shadow-md">
        <div className="space-y-4">
          {/* Expert Notebook header */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gradient-to-l from-indigo-50 to-purple-50 rounded-lg border border-indigo-100">
            <FileText className="w-4 h-4 text-indigo-500" />
            <span className="text-xs font-semibold text-indigo-700">פנקס מומחה — ניתוח סתירה</span>
          </div>

          {/* 1) Header with badges */}
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-warning-500" />
              <span className="font-bold text-slate-900">סתירה #{index + 1}</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant={getSeverityColor(severity) as any}>
                {getSeverityLabel(severity)}
              </Badge>
              <Badge variant="neutral">{getTypeLabel(contradictionType)}</Badge>
              {getCategoryLabel(contradiction.category) && (
                <Badge variant={getCategoryColor(contradiction.category) as any}>
                  {getCategoryLabel(contradiction.category)}
                </Badge>
              )}
              {contradiction.verified && (
                <Badge variant="success">מאומת</Badge>
              )}
            </div>
          </div>

          {/* 2) Claims with context + speaker/plane badges (§10a, §10b) */}
          <div className="space-y-3">
            <ClaimPanel
              label="טענה א'"
              color="red"
              claim={contradiction.claim_a}
              evidence={ev1}
            />
            <div className="flex justify-center">
              <div className="w-8 h-8 rounded-full bg-warning-100 flex items-center justify-center">
                <ArrowDown className="w-4 h-4 text-warning-600" />
              </div>
            </div>
            <ClaimPanel
              label="טענה ב'"
              color="orange"
              claim={contradiction.claim_b}
              evidence={ev2}
            />
          </div>

          {/* 3) Gate checks with pass/fail indicators (§10c) — always visible */}
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <button
              onClick={() => setGatesOpen(!gatesOpen)}
              className="w-full flex items-center justify-between px-4 py-2 bg-slate-50 hover:bg-slate-100 transition-colors"
            >
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <Shield className="w-4 h-4" />
                <span>בדיקות שערים {gates && Object.keys(gates).length > 0 ? `(${Object.keys(gates).length})` : ''}</span>
              </div>
              {gatesOpen ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </button>
            {gatesOpen && (
              gates && Object.keys(gates).length > 0 ? (
                <div className="p-3 grid grid-cols-2 gap-2">
                  {Object.entries(gates).map(([key, val]) => {
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
                          {gateLabels[key] || key}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-3 text-xs text-slate-400 text-center">
                  לא בוצעו בדיקות שערים עבור סתירה זו
                </div>
              )
            )}
          </div>

          {/* 4) Reconciliation attempt (§10d) — always visible */}
          <div className="p-3 bg-indigo-50 rounded-xl border border-indigo-100">
            <div className="text-xs text-indigo-600 font-medium mb-1 flex items-center gap-1">
              <Search className="w-3 h-3" />
              ניסיון יישוב
            </div>
            {contradiction.reconciliation_attempt ? (
              <p className="text-sm text-slate-700">{contradiction.reconciliation_attempt}</p>
            ) : contradiction.reconciler_rationale ? null : (
              <p className="text-sm text-slate-400 italic">לא בוצע ניסיון יישוב</p>
            )}
            {contradiction.reconciler_rationale && (
              <p className="text-sm text-indigo-800 mt-1">{contradiction.reconciler_rationale}</p>
            )}
            {contradiction.deciding_fields && contradiction.deciding_fields.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {contradiction.deciding_fields.map((f) => (
                  <span key={f} className="text-[10px] px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded">
                    {f}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* 5) Final decision with lock indicator (§10e) */}
          <div className="p-4 bg-slate-50 rounded-xl">
            <div className="flex items-center gap-2 mb-1">
              <Lock className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs text-slate-500 font-medium">החלטה סופית</span>
            </div>
            <p className="text-slate-700">{getExplanation()}</p>
          </div>

          {/* 6) Hard UI stops — Mark as contradiction button (§10f) */}
          <div className="flex items-center justify-between">
            <button
              disabled={markDisabled}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                markDisabled
                  ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                  : 'bg-red-600 text-white hover:bg-red-700'
              }`}
              title={markDisabled ? `חסום: ${disableReasons.join(', ')}` : 'סמן כסתירה'}
            >
              <AlertTriangle className="w-4 h-4" />
              סמן כסתירה
            </button>
            {markDisabled && disableReasons.length > 0 && (
              <span className="text-xs text-slate-400 flex items-center gap-1">
                <Lock className="w-3 h-3" />
                {disableReasons.join(' | ')}
              </span>
            )}
          </div>

          {/* Confidence */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span>ביטחון ניתוח:</span>
              <div className="flex-1 h-2 bg-slate-200 rounded-full max-w-32">
                <div
                  className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full"
                  style={{ width: `${(contradiction.confidence || 0) * 100}%` }}
                />
              </div>
              <span className="font-medium">
                {Math.round((contradiction.confidence || 0) * 100)}%
              </span>
            </div>
            {contradiction.verifier_confidence != null && (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span>ביטחון מאמת:</span>
                <div className="flex-1 h-2 bg-slate-200 rounded-full max-w-32">
                  <div
                    className="h-full bg-gradient-to-r from-green-500 to-emerald-500 rounded-full"
                    style={{ width: `${(contradiction.verifier_confidence || 0) * 100}%` }}
                  />
                </div>
                <span className="font-medium text-green-700">
                  {Math.round((contradiction.verifier_confidence || 0) * 100)}%
                </span>
              </div>
            )}
          </div>
        </div>
      </Card>
    </motion.div>
  );
};

// Question Card Component
const QuestionCard: React.FC<{
  question: CrossExamQuestion;
  index: number;
  onCopy: (text: string) => void;
}> = ({ question, index, onCopy }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    onCopy(question.question);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
    >
      <Card>
        <div className="space-y-3">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-600 font-bold text-sm">
                {index + 1}
              </div>
              <span className="text-xs text-slate-500">{question.strategy || 'שאלה'}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopy}
              leftIcon={copied ? <CheckCircle className="w-4 h-4 text-success-500" /> : <Copy className="w-4 h-4" />}
            >
              {copied ? 'הועתק!' : 'העתק'}
            </Button>
          </div>

          <p className="text-lg text-slate-900 font-medium">{question.question}</p>

          {question.purpose && (
            <p className="text-sm text-slate-500">
              <span className="font-medium">מטרה:</span> {question.purpose}
            </p>
          )}

          {/* Show follow-up question if available */}
          {(question.follow_up || (question.follow_ups && question.follow_ups.length > 0)) && (
            <div className="pt-3 border-t border-slate-100">
              <p className="text-xs text-slate-500 font-medium mb-2">שאלות המשך:</p>
              <ul className="space-y-1">
                {question.follow_up && (
                  <li className="text-sm text-slate-600 flex items-start gap-2">
                    <span className="text-slate-400">•</span>
                    {question.follow_up}
                  </li>
                )}
                {question.follow_ups?.map((followUp, i) => (
                  <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                    <span className="text-slate-400">•</span>
                    {followUp}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Card>
    </motion.div>
  );
};

export default AnalyzePage;
