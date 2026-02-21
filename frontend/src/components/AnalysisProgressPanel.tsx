import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle,
  Circle,
  Loader2,
  FileText,
  AlertTriangle,
  Search,
  Brain,
  ShieldCheck,
  Save,
  Lightbulb,
  Flag,
} from 'lucide-react';
import { Card, Badge, Progress } from './ui';
import { getAccessToken } from '../api/client';
import type {
  StructuredProgress,
  ProgressStage,
  ProgressPreview,
  PreviewContradiction,
} from '../types';

// ── Stage icon mapping ──
const stageIcons: Record<string, React.ReactNode> = {
  load_docs: <FileText className="w-4 h-4" />,
  extract_claims: <Search className="w-4 h-4" />,
  build_graphs: <Brain className="w-4 h-4" />,
  learn_context: <Lightbulb className="w-4 h-4" />,
  detect_rules: <AlertTriangle className="w-4 h-4" />,
  detect_llm: <Brain className="w-4 h-4" />,
  verify: <ShieldCheck className="w-4 h-4" />,
  score_save: <Save className="w-4 h-4" />,
  insights: <Lightbulb className="w-4 h-4" />,
  complete: <Flag className="w-4 h-4" />,
};

// ── Severity colors ──
const severityColor: Record<string, string> = {
  critical: 'text-red-600 bg-red-50 border-red-200',
  high: 'text-red-500 bg-red-50 border-red-200',
  medium: 'text-orange-500 bg-orange-50 border-orange-200',
  low: 'text-yellow-600 bg-yellow-50 border-yellow-200',
};

const contradictionTypeLabels: Record<string, string> = {
  TEMPORAL_DATE: 'תאריכים',
  QUANTITATIVE_AMOUNT: 'כמויות',
  ACTOR_ATTRIBUTION: 'זיהוי מבצע',
  PRESENCE_PARTICIPATION: 'נוכחות',
  DOCUMENT_EXISTENCE: 'קיום מסמך',
  IDENTITY_BASIC: 'זהות',
};

// ── Hook: useJobProgressStream ──
export function useJobProgressStream(
  jobId: string | null,
  baseUrl?: string
): {
  progress: StructuredProgress | null;
  isConnected: boolean;
} {
  const [progress, setProgress] = useState<StructuredProgress | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);

  const connect = useCallback(() => {
    if (!jobId) return;

    const token = getAccessToken();
    const base = baseUrl || '';
    // EventSource doesn't support custom headers, so we pass token as query param
    const url = `${base}/api/v1/jobs/${jobId}/stream${token ? `?token=${token}` : ''}`;

    // Use fetch-based SSE since we need auth
    const controller = new AbortController();

    const fetchStream = async () => {
      try {
        const resp = await fetch(url, {
          headers: {
            Authorization: token ? `Bearer ${token}` : '',
          },
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          throw new Error(`SSE connection failed: ${resp.status}`);
        }

        setIsConnected(true);
        retryCountRef.current = 0;

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6)) as StructuredProgress;
                setProgress(data);

                // If final, we're done
                if (data.final) {
                  setIsConnected(false);
                  return;
                }
              } catch {
                // Skip malformed JSON
              }
            }
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        setIsConnected(false);

        // Retry with backoff (max 4 retries)
        if (retryCountRef.current < 4) {
          const delay = Math.pow(2, retryCountRef.current) * 1000;
          retryCountRef.current++;
          setTimeout(connect, delay);
        }
      }
    };

    fetchStream();

    // Store abort controller for cleanup
    eventSourceRef.current = { close: () => controller.abort() } as unknown as EventSource;
  }, [jobId, baseUrl]);

  useEffect(() => {
    connect();
    return () => {
      eventSourceRef.current?.close();
    };
  }, [connect]);

  return { progress, isConnected };
}

// ── Hook: useJobProgressPolling (fallback) ──
export function useJobProgressPolling(
  jobId: string | null,
  getJobStatus: (jobId: string) => Promise<{ progress?: number; structured_progress?: StructuredProgress; status: string }>,
  intervalMs = 1500
): {
  progress: StructuredProgress | null;
} {
  const [progress, setProgress] = useState<StructuredProgress | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      try {
        const status = await getJobStatus(jobId);
        if (status.structured_progress) {
          setProgress(status.structured_progress);
        } else if (status.progress !== undefined) {
          // Fallback: create minimal structured progress from legacy data
          setProgress((prev) => ({
            overall_pct: status.progress || 0,
            current_stage: null,
            current_stage_label: '',
            elapsed_sec: prev?.elapsed_sec ? prev.elapsed_sec + intervalMs / 1000 : 0,
            stages: prev?.stages || [],
            preview: prev?.preview || {
              documents_total: 0,
              documents_processed: 0,
              claims_extracted: 0,
              contradictions_found: 0,
              contradictions_verified: 0,
              contradictions_rejected: 0,
              first_contradictions: [],
            },
            error: null,
            job_status: status.status,
          }));
        }

        if (status.status === 'finished' || status.status === 'failed') {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch {
        // Ignore polling errors
      }
    };

    poll();
    intervalRef.current = setInterval(poll, intervalMs);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [jobId, getJobStatus, intervalMs]);

  return { progress };
}

// ── Stage row component ──
const StageRow: React.FC<{ stage: ProgressStage; isCurrent: boolean }> = ({
  stage,
  isCurrent,
}) => {
  const isDone = stage.finished_at > 0;
  const icon = stageIcons[stage.key] || <Circle className="w-4 h-4" />;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className={`flex items-center gap-3 py-2 px-3 rounded-lg transition-colors ${
        isCurrent
          ? 'bg-primary-50 border border-primary-200'
          : isDone
          ? 'bg-green-50/50'
          : 'opacity-40'
      }`}
    >
      {/* Status icon */}
      <div className="flex-shrink-0">
        {isDone ? (
          <CheckCircle className="w-5 h-5 text-green-500" />
        ) : isCurrent ? (
          <Loader2 className="w-5 h-5 text-primary-500 animate-spin" />
        ) : (
          <Circle className="w-5 h-5 text-slate-300" />
        )}
      </div>

      {/* Stage icon + label */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className={isCurrent ? 'text-primary-600' : isDone ? 'text-green-700' : 'text-slate-400'}>
          {icon}
        </span>
        <span
          className={`text-sm font-medium truncate ${
            isCurrent ? 'text-primary-900' : isDone ? 'text-slate-700' : 'text-slate-400'
          }`}
        >
          {stage.label_he}
        </span>
      </div>

      {/* Detail text */}
      {stage.detail && (isCurrent || isDone) && (
        <span className="text-xs text-slate-500 flex-shrink-0">{stage.detail}</span>
      )}

      {/* Duration */}
      {isDone && stage.elapsed_sec !== undefined && (
        <span className="text-xs text-slate-400 flex-shrink-0 tabular-nums">
          {stage.elapsed_sec < 1 ? '<1' : Math.round(stage.elapsed_sec)}s
        </span>
      )}

      {/* In-stage progress bar */}
      {isCurrent && stage.progress_pct > 0 && stage.progress_pct < 100 && (
        <div className="w-16 flex-shrink-0">
          <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-primary-500 rounded-full"
              animate={{ width: `${stage.progress_pct}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>
      )}
    </motion.div>
  );
};

// ── Preview counters component ──
const PreviewCounters: React.FC<{ preview: ProgressPreview }> = ({ preview }) => {
  const counters = [
    { label: 'מסמכים', value: `${preview.documents_processed}/${preview.documents_total}`, show: preview.documents_total > 0 },
    { label: 'טענות', value: preview.claims_extracted, show: preview.claims_extracted > 0 },
    { label: 'סתירות', value: preview.contradictions_found, show: preview.contradictions_found > 0 },
    { label: 'אומתו', value: preview.contradictions_verified, show: preview.contradictions_verified > 0 },
    { label: 'נדחו', value: preview.contradictions_rejected, show: preview.contradictions_rejected > 0 },
  ].filter((c) => c.show);

  if (counters.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-3">
      {counters.map((c) => (
        <div key={c.label} className="flex flex-col items-center px-3 py-2 bg-white rounded-lg border border-slate-200 min-w-[70px]">
          <span className="text-lg font-bold text-slate-900 tabular-nums">{c.value}</span>
          <span className="text-[10px] text-slate-500 font-medium">{c.label}</span>
        </div>
      ))}
    </div>
  );
};

// ── Preview contradiction card ──
const PreviewContradictionCard: React.FC<{
  contradiction: PreviewContradiction;
  index: number;
}> = ({ contradiction, index }) => {
  const typeLabel = contradictionTypeLabels[contradiction.type] || contradiction.type;
  const sevClass = severityColor[contradiction.severity] || severityColor.medium;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      className="p-3 bg-white rounded-lg border border-slate-200 space-y-2"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-3.5 h-3.5 text-orange-500 flex-shrink-0" />
        <span className="text-xs font-medium text-slate-600">#{index + 1}</span>
        <Badge variant="neutral" size="sm">{typeLabel}</Badge>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sevClass}`}>
          {contradiction.severity}
        </span>
        <span className="text-xs text-slate-400 mr-auto tabular-nums">
          {Math.round(contradiction.confidence * 100)}%
        </span>
      </div>
      <div className="space-y-1">
        <p className="text-xs text-slate-700 leading-relaxed line-clamp-2" dir="rtl">
          <span className="font-medium text-red-600">א׳: </span>
          {contradiction.claim_a}
        </p>
        <p className="text-xs text-slate-700 leading-relaxed line-clamp-2" dir="rtl">
          <span className="font-medium text-orange-600">ב׳: </span>
          {contradiction.claim_b}
        </p>
      </div>
    </motion.div>
  );
};

// ── Main AnalysisProgressPanel ──
interface AnalysisProgressPanelProps {
  progress: StructuredProgress | null;
  isAnalyzing: boolean;
  /** Fallback legacy progress % when structured is not available */
  legacyProgress?: number;
}

export const AnalysisProgressPanel: React.FC<AnalysisProgressPanelProps> = ({
  progress,
  isAnalyzing,
  legacyProgress = 0,
}) => {
  if (!isAnalyzing && !progress) return null;

  const pct = progress?.overall_pct ?? legacyProgress;
  const hasStructured = progress && progress.stages && progress.stages.length > 0;

  return (
    <Card className="overflow-hidden">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Loader2 className="w-5 h-5 text-primary-500 animate-spin" />
            <span className="font-bold text-slate-900">
              {progress?.current_stage_label || 'מנתח מסמכים...'}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {progress?.elapsed_sec !== undefined && (
              <span className="text-xs text-slate-400 tabular-nums">
                {Math.floor(progress.elapsed_sec / 60)}:{String(Math.floor(progress.elapsed_sec % 60)).padStart(2, '0')}
              </span>
            )}
            <span className="text-sm font-bold text-primary-600 tabular-nums">{pct}%</span>
          </div>
        </div>

        {/* Overall progress bar */}
        <Progress value={pct} animated variant="primary" size="lg" />

        {/* Structured stages timeline */}
        {hasStructured && (
          <div className="space-y-1">
            <AnimatePresence>
              {progress.stages.map((stage) => (
                <StageRow
                  key={stage.key}
                  stage={stage}
                  isCurrent={stage.key === progress.current_stage}
                />
              ))}
            </AnimatePresence>
          </div>
        )}

        {/* Live counters */}
        {progress?.preview && (
          <PreviewCounters preview={progress.preview} />
        )}

        {/* Preview contradictions */}
        {progress?.preview?.first_contradictions &&
          progress.preview.first_contradictions.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-orange-500" />
                <span className="text-sm font-medium text-slate-700">
                  ממצאים ראשוניים (תצוגה מקדימה)
                </span>
              </div>
              <div className="space-y-2">
                {progress.preview.first_contradictions.map((c, i) => (
                  <PreviewContradictionCard key={i} contradiction={c} index={i} />
                ))}
              </div>
            </div>
          )}

        {/* Error */}
        {progress?.error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {progress.error}
          </div>
        )}
      </div>
    </Card>
  );
};

export default AnalysisProgressPanel;
