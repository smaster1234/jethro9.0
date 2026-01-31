import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import {
  Clock,
  FileText,
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  RefreshCw,
  Ban,
  PlusCircle,
  CheckCircle,
  Star,
  Paperclip,
  Loader2,
  Filter,
} from 'lucide-react';
import { documentsApi, casesApi } from '../../api';
import { Card, Badge, EmptyState } from '../../components/ui';
import { cn } from '../../utils/cn';
import type { Case, Document } from '../../types';

/** Version change types matching the backend VersionChangeType enum */
type VersionChangeType =
  | 'consistent'
  | 'expanded'
  | 'reduced'
  | 'changed'
  | 'omitted_significant'
  | 'omitted_ignored'
  | 'new'
  | 'contradiction';

interface TimelineEntry {
  docId: string;
  docName: string;
  docRole: string;
  docParty: string;
  docDate: string | null;
  isCompleteness: boolean;
  claimCount: number;
  findings: TimelineFinding[];
}

interface TimelineFinding {
  type: VersionChangeType;
  summary: string;
  detail?: string;
  severity?: 'critical' | 'high' | 'medium' | 'low';
}

const CHANGE_TYPE_CONFIG: Record<
  VersionChangeType,
  { icon: typeof AlertTriangle; label: string; color: string; bg: string }
> = {
  contradiction: {
    icon: AlertTriangle,
    label: 'סתירה',
    color: 'text-danger-600',
    bg: 'bg-danger-50 border-danger-200',
  },
  omitted_significant: {
    icon: Ban,
    label: 'השמטה ממקור ראשי',
    color: 'text-warning-600',
    bg: 'bg-warning-50 border-warning-200',
  },
  reduced: {
    icon: TrendingDown,
    label: 'צמצום',
    color: 'text-orange-600',
    bg: 'bg-orange-50 border-orange-200',
  },
  expanded: {
    icon: TrendingUp,
    label: 'הרחבה',
    color: 'text-blue-600',
    bg: 'bg-blue-50 border-blue-200',
  },
  changed: {
    icon: RefreshCw,
    label: 'שינוי',
    color: 'text-purple-600',
    bg: 'bg-purple-50 border-purple-200',
  },
  new: {
    icon: PlusCircle,
    label: 'הוספה',
    color: 'text-accent-600',
    bg: 'bg-accent-50 border-accent-200',
  },
  consistent: {
    icon: CheckCircle,
    label: 'עקבי',
    color: 'text-success-600',
    bg: 'bg-success-50 border-success-200',
  },
  omitted_ignored: {
    icon: Paperclip,
    label: 'לא רלוונטי',
    color: 'text-slate-400',
    bg: 'bg-slate-50 border-slate-200',
  },
};

const COMPLETENESS_ROLES = new Set([
  'statement_of_claim',
  'defense',
  'reply',
  'affidavit',
  'summations',
]);

const ROLE_MAP: Record<string, string> = {
  statement_of_claim: 'כתב תביעה',
  defense: 'כתב הגנה',
  reply: 'כתב תשובה',
  motion: 'בקשה',
  response: 'תגובה',
  summations: 'סיכומים',
  affidavit: 'תצהיר',
  exhibit: 'נספח',
  expert_opinion: 'חוות דעת',
  contract: 'חוזה',
  letter: 'מכתב',
  protocol: 'פרוטוקול',
  judgment: 'פסק דין',
  unknown: 'מסמך',
};

const PARTY_MAP: Record<string, string> = {
  ours: 'שלנו',
  theirs: 'צד שכנגד',
  court: 'בית משפט',
  third_party: 'צד שלישי',
};

export const TimelineTab: React.FC = () => {
  const { notebookId } = useParams();
  const { notebook } = useOutletContext<{ notebook: Case }>();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filterParty, setFilterParty] = useState<'all' | 'ours' | 'theirs'>('all');
  const [showChangesOnly, setShowChangesOnly] = useState(false);

  useEffect(() => {
    if (!notebookId) return;
    const fetch = async () => {
      setIsLoading(true);
      try {
        const docs = await documentsApi.list(notebookId);
        setDocuments(docs);
      } catch {
        // silently fail
      } finally {
        setIsLoading(false);
      }
    };
    fetch();
  }, [notebookId]);

  // Build timeline entries sorted by date
  const timeline = useMemo(() => {
    const entries: TimelineEntry[] = documents.map((doc) => ({
      docId: doc.id,
      docName: doc.doc_name,
      docRole: doc.role || 'unknown',
      docParty: doc.party || 'unknown',
      docDate: doc.created_at,
      isCompleteness: COMPLETENESS_ROLES.has(doc.role || ''),
      claimCount: 0, // Will be populated when we have analysis data
      findings: [], // Will be populated from version tracking
    }));

    // Sort by date
    entries.sort((a, b) => {
      if (!a.docDate && !b.docDate) return 0;
      if (!a.docDate) return 1;
      if (!b.docDate) return -1;
      return new Date(a.docDate).getTime() - new Date(b.docDate).getTime();
    });

    return entries;
  }, [documents]);

  const filteredTimeline = timeline.filter((entry) => {
    if (filterParty !== 'all' && entry.docParty !== filterParty) return false;
    if (showChangesOnly && entry.findings.length === 0) return false;
    return true;
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="p-6">
        <EmptyState
          icon={<Clock className="w-12 h-12" />}
          title="אין מסמכים בציר הזמן"
          description="העלו מסמכים בלשונית 'מקורות' כדי לבנות את ציר הזמן"
        />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header + Filters */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900">ציר הזמן</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {documents.length} מסמכים · מעקב שינויי גירסה עובדתית
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1">
            {(['all', 'ours', 'theirs'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilterParty(f)}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                  filterParty === f
                    ? 'bg-primary-100 text-primary-700'
                    : 'text-slate-500 hover:text-slate-700'
                )}
              >
                {f === 'all' ? 'כל הצדדים' : f === 'ours' ? 'שלנו' : 'צד שכנגד'}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowChangesOnly(!showChangesOnly)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
              showChangesOnly
                ? 'bg-warning-50 border-warning-200 text-warning-700'
                : 'bg-white border-slate-200 text-slate-500 hover:text-slate-700'
            )}
          >
            <Filter className="w-3.5 h-3.5" />
            שינויים בלבד
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute right-[22px] top-0 bottom-0 w-0.5 bg-slate-200" />

        <div className="space-y-0">
          {filteredTimeline.map((entry, idx) => (
            <div key={entry.docId} className="relative flex gap-4 pb-8">
              {/* Timeline dot */}
              <div
                className={cn(
                  'relative z-10 w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0 border-2',
                  entry.isCompleteness
                    ? 'bg-warning-50 border-warning-300'
                    : 'bg-white border-slate-200'
                )}
              >
                {entry.isCompleteness ? (
                  <Star className="w-5 h-5 text-warning-500" />
                ) : (
                  <FileText className="w-5 h-5 text-slate-400" />
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                {/* Date label */}
                <div className="text-[11px] text-slate-400 mb-1">
                  {entry.docDate
                    ? new Date(entry.docDate).toLocaleDateString('he-IL', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })
                    : 'תאריך לא ידוע'}
                </div>

                {/* Document card */}
                <Card className="!p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-slate-900">
                          {ROLE_MAP[entry.docRole] || entry.docRole}
                        </h3>
                        <Badge
                          variant={entry.docParty === 'ours' ? 'primary' : 'neutral'}
                          className="text-[10px]"
                        >
                          {PARTY_MAP[entry.docParty] || entry.docParty}
                        </Badge>
                        {entry.isCompleteness && (
                          <Badge variant="warning" className="text-[10px]">
                            שלמות
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">{entry.docName}</p>
                    </div>
                    {entry.claimCount > 0 && (
                      <span className="text-xs text-slate-400">{entry.claimCount} טענות</span>
                    )}
                  </div>

                  {/* Findings */}
                  {entry.findings.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {entry.findings.map((finding, fi) => {
                        const config = CHANGE_TYPE_CONFIG[finding.type];
                        const Icon = config.icon;
                        return (
                          <div
                            key={fi}
                            className={cn('flex items-start gap-2 p-2.5 rounded-lg border', config.bg)}
                          >
                            <Icon className={cn('w-4 h-4 mt-0.5 flex-shrink-0', config.color)} />
                            <div className="flex-1 min-w-0">
                              <span className={cn('text-xs font-medium', config.color)}>
                                {config.label}:
                              </span>
                              <span className="text-xs text-slate-700 mr-1">{finding.summary}</span>
                              {finding.detail && (
                                <p className="text-[11px] text-slate-500 mt-0.5">{finding.detail}</p>
                              )}
                            </div>
                            {finding.severity && (
                              <Badge
                                variant={
                                  finding.severity === 'critical'
                                    ? 'danger'
                                    : finding.severity === 'high'
                                    ? 'warning'
                                    : 'neutral'
                                }
                                className="text-[10px]"
                              >
                                {finding.severity}
                              </Badge>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Placeholder for when we don't have findings yet */}
                  {entry.findings.length === 0 && (
                    <p className="text-[11px] text-slate-400 mt-2">
                      הרצת ניתוח תחשוף שינויי גירסה עובדתית
                    </p>
                  )}
                </Card>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default TimelineTab;
