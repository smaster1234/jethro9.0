import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  FileText,
  Upload,
  AlertCircle,
  CheckCircle,
  Clock,
  Star,
  Paperclip,
  Loader2,
} from 'lucide-react';
import { documentsApi } from '../../api';
import { Card, Badge, EmptyState } from '../../components/ui';
import { cn } from '../../utils/cn';
import type { Case, Document } from '../../types';

/** Document class for completeness analysis */
type DocClass = 'primary_pleading' | 'affidavit' | 'summation' | 'motion' | 'supporting';

interface DocClassOption {
  value: DocClass;
  label: string;
  description: string;
  icon: typeof Star | typeof Paperclip;
  completeness: boolean;
}

const DOC_CLASS_OPTIONS: DocClassOption[] = [
  {
    value: 'primary_pleading',
    label: 'כתב טענות ראשי',
    description: 'תביעה, הגנה, עתירה, תשובה',
    icon: Star,
    completeness: true,
  },
  {
    value: 'affidavit',
    label: 'תצהיר עדות ראשית',
    description: 'תצהיר עד',
    icon: Star,
    completeness: true,
  },
  {
    value: 'summation',
    label: 'סיכומים',
    description: 'סיכומי טענות',
    icon: Star,
    completeness: true,
  },
  {
    value: 'motion',
    label: 'בקשה / כתב טענות משני',
    description: 'בקשות — אין חובת שלמות',
    icon: Paperclip,
    completeness: false,
  },
  {
    value: 'supporting',
    label: 'מסמך נלווה',
    description: 'חוו"ד, נספח, חוזה, מכתב',
    icon: Paperclip,
    completeness: false,
  },
];

const PARTY_OPTIONS = [
  { value: 'ours', label: 'שלנו' },
  { value: 'theirs', label: 'צד שכנגד' },
  { value: 'court', label: 'בית משפט' },
  { value: 'third_party', label: 'צד שלישי' },
];

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
  unknown: 'לא ידוע',
};

interface UploadFormState {
  isOpen: boolean;
  files: File[];
  docClass: DocClass;
  party: string;
  role: string;
  author: string;
  occurredAt: string;
  isUploading: boolean;
}

export const SourcesTab: React.FC = () => {
  const { notebookId } = useParams();
  useOutletContext<{ notebook: Case }>();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [upload, setUpload] = useState<UploadFormState>({
    isOpen: false,
    files: [],
    docClass: 'primary_pleading',
    party: 'ours',
    role: 'statement_of_claim',
    author: '',
    occurredAt: '',
    isUploading: false,
  });

  const fetchDocuments = useCallback(async () => {
    if (!notebookId) return;
    try {
      const docs = await documentsApi.list(notebookId);
      setDocuments(docs);
    } catch {
      // silently fail
    } finally {
      setIsLoading(false);
    }
  }, [notebookId]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files || []);
    setUpload((prev) => ({ ...prev, files: selected, isOpen: true }));
  };

  const handleUpload = async () => {
    if (!notebookId || upload.files.length === 0) return;
    setUpload((prev) => ({ ...prev, isUploading: true }));
    try {
      const metadata = upload.files.map(() => ({
        party: upload.party,
        role: upload.role,
        author: upload.author || undefined,
      }));
      await documentsApi.upload(notebookId, upload.files, metadata);
      setUpload({
        isOpen: false,
        files: [],
        docClass: 'primary_pleading',
        party: 'ours',
        role: 'statement_of_claim',
        author: '',
        occurredAt: '',
        isUploading: false,
      });
      await fetchDocuments();
    } catch {
      setUpload((prev) => ({ ...prev, isUploading: false }));
    }
  };

  // Group documents by doc_class
  const grouped = {
    primary: documents.filter((d) =>
      ['statement_of_claim', 'defense', 'reply'].includes(d.role || '')
    ),
    affidavit: documents.filter((d) => d.role === 'affidavit'),
    summation: documents.filter((d) => d.role === 'summations'),
    motion: documents.filter((d) => ['motion', 'response'].includes(d.role || '')),
    supporting: documents.filter(
      (d) =>
        !['statement_of_claim', 'defense', 'reply', 'affidavit', 'summations', 'motion', 'response'].includes(
          d.role || ''
        )
    ),
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case 'completed':
      case 'ready':
        return <CheckCircle className="w-4 h-4 text-success-500" />;
      case 'processing':
        return <Loader2 className="w-4 h-4 text-primary-500 animate-spin" />;
      case 'failed':
        return <AlertCircle className="w-4 h-4 text-danger-500" />;
      default:
        return <Clock className="w-4 h-4 text-slate-400" />;
    }
  };

  const renderDocGroup = (
    title: string,
    docs: Document[],
    isCompleteness: boolean,
    iconEl: React.ReactNode
  ) => {
    if (docs.length === 0) return null;
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
          {iconEl}
          <span>{title}</span>
          {isCompleteness && (
            <Badge variant="warning" className="text-[10px]">
              חובת שלמות
            </Badge>
          )}
          <span className="text-slate-400 text-xs">({docs.length})</span>
        </div>
        <div className="space-y-1.5 mr-6">
          {docs.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center gap-3 px-3 py-2.5 bg-white rounded-lg border border-slate-100 hover:border-slate-200 transition-colors cursor-pointer"
            >
              {statusIcon(doc.status)}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 truncate">{doc.doc_name}</p>
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <span>{ROLE_MAP[doc.role || 'unknown'] || doc.role}</span>
                  {doc.party && <span>· {doc.party === 'ours' ? 'שלנו' : doc.party === 'theirs' ? 'צד שכנגד' : doc.party}</span>}
                  {doc.page_count && <span>· {doc.page_count} עמודים</span>}
                </div>
              </div>
              {doc.created_at && (
                <span className="text-[11px] text-slate-400">
                  {new Date(doc.created_at).toLocaleDateString('he-IL')}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    );
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
      {/* Upload area */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-900">מקורות</h2>
          <div className="flex items-center gap-2">
            <label className="cursor-pointer">
              <input
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
                className="hidden"
                onChange={handleFileSelect}
              />
              <div className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium">
                <Upload className="w-4 h-4" />
                העלה מסמכים
              </div>
            </label>
          </div>
        </div>

        {/* Upload form */}
        {upload.isOpen && upload.files.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            className="border-t border-slate-100 pt-4 space-y-4"
          >
            <div className="bg-slate-50 rounded-lg p-4 space-y-3">
              <p className="text-sm font-medium text-slate-700">
                {upload.files.length} קבצים נבחרו: {upload.files.map((f) => f.name).join(', ')}
              </p>

              {/* Doc class picker */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1.5">סוג מסמך</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {DOC_CLASS_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setUpload((p) => ({ ...p, docClass: opt.value }))}
                      className={cn(
                        'flex items-start gap-2 p-3 rounded-lg border text-right transition-colors',
                        upload.docClass === opt.value
                          ? 'border-primary-400 bg-primary-50'
                          : 'border-slate-200 bg-white hover:border-slate-300'
                      )}
                    >
                      <opt.icon
                        className={cn(
                          'w-4 h-4 mt-0.5 flex-shrink-0',
                          opt.completeness ? 'text-warning-500' : 'text-slate-400'
                        )}
                      />
                      <div>
                        <p className="text-sm font-medium">{opt.label}</p>
                        <p className="text-[11px] text-slate-500">{opt.description}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Party + Date */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">צד</label>
                  <select
                    value={upload.party}
                    onChange={(e) => setUpload((p) => ({ ...p, party: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  >
                    {PARTY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">תאריך מסמך</label>
                  <input
                    type="date"
                    value={upload.occurredAt}
                    onChange={(e) => setUpload((p) => ({ ...p, occurredAt: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">מחבר/מצהיר</label>
                  <input
                    type="text"
                    value={upload.author}
                    onChange={(e) => setUpload((p) => ({ ...p, author: e.target.value }))}
                    placeholder="שם"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setUpload((p) => ({ ...p, isOpen: false, files: [] }))}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800"
                >
                  ביטול
                </button>
                <button
                  onClick={handleUpload}
                  disabled={upload.isUploading}
                  className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm font-medium disabled:opacity-50"
                >
                  {upload.isUploading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Upload className="w-4 h-4" />
                  )}
                  העלה
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </Card>

      {/* Documents grouped by class */}
      {documents.length === 0 ? (
        <EmptyState
          icon={<FileText className="w-12 h-12" />}
          title="אין מסמכים עדיין"
          description="העלו מסמכים כדי להתחיל בניתוח"
        />
      ) : (
        <div className="space-y-5">
          {renderDocGroup(
            'כתבי טענות ראשיים',
            grouped.primary,
            true,
            <Star className="w-4 h-4 text-warning-500" />
          )}
          {renderDocGroup(
            'תצהירי עדות ראשית',
            grouped.affidavit,
            true,
            <Star className="w-4 h-4 text-warning-500" />
          )}
          {renderDocGroup(
            'סיכומים',
            grouped.summation,
            true,
            <Star className="w-4 h-4 text-warning-500" />
          )}
          {renderDocGroup(
            'בקשות וכתבי טענות משניים',
            grouped.motion,
            false,
            <Paperclip className="w-4 h-4 text-slate-400" />
          )}
          {renderDocGroup(
            'מסמכים נלווים',
            grouped.supporting,
            false,
            <Paperclip className="w-4 h-4 text-slate-400" />
          )}
        </div>
      )}
    </div>
  );
};

export default SourcesTab;
