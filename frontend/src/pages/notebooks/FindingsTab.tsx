import React, { useEffect, useState } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle,
  Loader2,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Clock,
  Shield,
} from 'lucide-react';
import { casesApi } from '../../api';
import { Card, Badge, EmptyState } from '../../components/ui';
import { cn } from '../../utils/cn';
import type { Case, AnalysisRun, Contradiction } from '../../types';

const SEVERITY_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  critical: { color: 'text-danger-700', bg: 'bg-danger-50 border-danger-200', label: 'קריטי' },
  high: { color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200', label: 'גבוה' },
  medium: { color: 'text-warning-700', bg: 'bg-warning-50 border-warning-200', label: 'בינוני' },
  low: { color: 'text-slate-600', bg: 'bg-slate-50 border-slate-200', label: 'נמוך' },
};

const TYPE_LABELS: Record<string, string> = {
  temporal_conflict: 'סתירה זמנית',
  quantitative_conflict: 'סתירה כמותית',
  presence_conflict: 'סתירת נוכחות',
  attribution_conflict: 'סתירת ייחוס',
  factual_conflict: 'סתירה עובדתית',
  temporal: 'זמנית',
  quant: 'כמותית',
  presence: 'נוכחות',
  actor: 'ייחוס',
  document: 'מסמך',
  identity: 'זהות',
};

const OUTCOME_LABELS: Record<string, { label: string; variant: string }> = {
  TRUE_CONTRADICTION: { label: 'סתירה אמיתית', variant: 'danger' },
  APPARENT_TENSION_RESOLVABLE: { label: 'ניתן ליישוב', variant: 'warning' },
  DISAGREEMENT_BETWEEN_PARTIES: { label: 'מחלוקת בין צדדים', variant: 'primary' },
  ROLE_OR_ATTRIBUTION_MISMATCH: { label: 'אי-התאמת ייחוס', variant: 'neutral' },
  PLANE_MISMATCH: { label: 'אי-התאמת מישור', variant: 'neutral' },
  TIME_OR_STAGE_SHIFT: { label: 'הבדל זמן/שלב', variant: 'neutral' },
  AMBIGUITY_OR_VAGUENESS: { label: 'עמימות', variant: 'neutral' },
  INSUFFICIENT_CONTEXT: { label: 'הקשר חסר', variant: 'neutral' },
  DUPLICATE_OR_RESTATEMENT: { label: 'כפילות', variant: 'neutral' },
};

export const FindingsTab: React.FC = () => {
  const { notebookId } = useParams();
  useOutletContext<{ notebook: Case }>();
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState<'all' | 'critical' | 'high'>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (!notebookId) return;
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const runsData = await casesApi.listRuns(notebookId, 20);
        setRuns(runsData);

        // Fetch full run details (with contradictions) for the latest completed run
        const latestCompleted = runsData.find((r) => r.status === 'completed');
        if (latestCompleted) {
          const fullRun = await casesApi.getRun(latestCompleted.id);
          setRuns((prev) =>
            prev.map((r) => (r.id === fullRun.id ? fullRun : r))
          );
        }
      } catch {
        // silently fail
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, [notebookId]);

  // Get contradictions from the latest completed run
  const latestRun = runs.find((r) => r.status === 'completed');
  const contradictions: Contradiction[] = latestRun?.contradictions || [];

  const filtered = contradictions.filter((c) => {
    if (filterSeverity === 'critical') return c.severity === 'critical';
    if (filterSeverity === 'high') return c.severity === 'critical' || c.severity === 'high';
    return true;
  });

  const stats = {
    total: contradictions.length,
    critical: contradictions.filter((c) => c.severity === 'critical').length,
    high: contradictions.filter((c) => c.severity === 'high').length,
    verified: contradictions.filter((c) => c.status === 'confirmed').length,
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'סה"כ ממצאים', value: stats.total, icon: AlertTriangle, color: 'primary' },
          { label: 'קריטיים', value: stats.critical, icon: AlertTriangle, color: 'danger' },
          { label: 'חומרה גבוהה', value: stats.high, icon: Shield, color: 'warning' },
          { label: 'מאומתים', value: stats.verified, icon: CheckCircle, color: 'success' },
        ].map((s) => (
          <Card key={s.label} className="!p-4">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  'w-10 h-10 rounded-lg flex items-center justify-center',
                  `bg-${s.color}-100`
                )}
              >
                <s.icon className={cn('w-5 h-5', `text-${s.color}-600`)} />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{s.value}</p>
                <p className="text-xs text-slate-500">{s.label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-900">ממצאים</h2>
        <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1">
          {(['all', 'high', 'critical'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilterSeverity(f)}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                filterSeverity === f
                  ? 'bg-primary-100 text-primary-700'
                  : 'text-slate-500 hover:text-slate-700'
              )}
            >
              {f === 'all' ? 'הכל' : f === 'high' ? 'גבוה+' : 'קריטי'}
            </button>
          ))}
        </div>
      </div>

      {/* Contradictions List */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle className="w-12 h-12" />}
          title={contradictions.length === 0 ? 'לא נמצאו ממצאים' : 'אין ממצאים בסינון זה'}
          description={
            contradictions.length === 0
              ? 'הריצו ניתוח כדי לחשוף סתירות ושינויי גירסה'
              : 'נסו סינון אחר'
          }
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((c, idx) => {
            const sev = c.severity || 'medium';
            const severity = SEVERITY_CONFIG[sev] || SEVERITY_CONFIG.medium;
            const isExpanded = expandedId === c.id;
            const outcomeKey = c.reconciler_outcome || '';
            const outcome = outcomeKey ? OUTCOME_LABELS[outcomeKey] : null;

            return (
              <Card
                key={c.id || idx}
                className={cn('!p-0 border', severity.bg, 'cursor-pointer')}
                onClick={() => setExpandedId(isExpanded ? null : c.id)}
              >
                {/* Header */}
                <div className="flex items-start justify-between p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className={cn('w-5 h-5 mt-0.5', severity.color)} />
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-slate-900">
                          סתירה #{idx + 1}
                        </span>
                        <Badge variant={sev === 'critical' ? 'danger' : sev === 'high' ? 'warning' : 'neutral'}>
                          {severity.label}
                        </Badge>
                        {c.type && TYPE_LABELS[c.type] && (
                          <Badge variant="neutral" className="text-[10px]">
                            {TYPE_LABELS[c.type]}
                          </Badge>
                        )}
                        {outcome && (
                          <Badge
                            variant={outcome.variant as 'danger' | 'warning' | 'primary' | 'neutral'}
                            className="text-[10px]"
                          >
                            {outcome.label}
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-slate-700 mt-1">{c.explanation || c.explanation_he || ''}</p>
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-400" />
                  )}
                </div>

                {/* Expanded content */}
                {isExpanded && (
                  <div className="px-4 pb-4 border-t border-slate-100 pt-3 space-y-3">
                    {/* Claim comparison */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-white rounded-lg p-3 border border-slate-100">
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <div className="w-2 h-2 rounded-full bg-primary-400" />
                          <span className="text-[11px] font-medium text-slate-500">מסמך א</span>
                        </div>
                        <p className="text-sm text-slate-800 leading-relaxed">
                          "{c.claim1_text || c.quote1 || ''}"
                        </p>
                      </div>
                      <div className="bg-white rounded-lg p-3 border border-slate-100">
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <div className="w-2 h-2 rounded-full bg-danger-400" />
                          <span className="text-[11px] font-medium text-slate-500">מסמך ב</span>
                        </div>
                        <p className="text-sm text-slate-800 leading-relaxed">
                          "{c.claim2_text || c.quote2 || ''}"
                        </p>
                      </div>
                    </div>

                    {/* Reconciliation */}
                    {(c.reconciliation_attempt || c.reconciler_rationale) && (
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-[11px] font-medium text-slate-500 mb-1">ניסיון יישוב:</p>
                        <p className="text-xs text-slate-700">
                          {c.reconciliation_attempt || c.reconciler_rationale}
                        </p>
                      </div>
                    )}

                    {/* Confidence */}
                    <div className="flex items-center gap-4 text-xs text-slate-500">
                      <span>ביטחון: {Math.round((c.confidence ?? 0.5) * 100)}%</span>
                      {c.bucket && (
                        <span>
                          סיווג:{' '}
                          {c.bucket === 'internal_ours'
                            ? 'פנימי שלנו'
                            : c.bucket === 'internal_theirs'
                            ? 'פנימי שלהם'
                            : c.bucket === 'dispute'
                            ? 'מחלוקת'
                            : c.bucket}
                        </span>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
                      <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors">
                        <Clock className="w-3.5 h-3.5" />
                        צפה בציר הזמן
                      </button>
                      <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-accent-600 bg-accent-50 rounded-lg hover:bg-accent-100 transition-colors">
                        <MessageSquare className="w-3.5 h-3.5" />
                        צור שאלת חקירה
                      </button>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default FindingsTab;
