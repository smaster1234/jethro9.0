import React, { useEffect, useState, useCallback } from 'react';
import { Outlet, useParams, useNavigate, NavLink, useLocation } from 'react-router-dom';
import {
  FileText,
  AlertTriangle,
  Target,
  Users,
  Clock,
  Play,
  Loader2,
  Upload,
  Plus,
  StickyNote,
  PanelLeftClose,
  PanelRightClose,
  Star,
} from 'lucide-react';
import { casesApi, documentsApi } from '../../api';
import { Spinner } from '../ui';
import { cn } from '../../utils/cn';
import type { Case, Document } from '../../types';

/* ─── Center tabs (not including Sources/Notes which are side panels) ─── */
const CENTER_TABS = [
  { id: 'findings', label: 'ממצאים', icon: AlertTriangle, path: 'findings' },
  { id: 'timeline', label: 'ציר זמן', icon: Clock, path: 'timeline' },
  { id: 'crossexam', label: 'חקירה', icon: Target, path: 'crossexam' },
  { id: 'witnesses', label: 'עדים', icon: Users, path: 'witnesses' },
] as const;

const DOC_CLASS_LABELS: Record<string, { label: string; icon: string }> = {
  primary_pleading: { label: 'כתב טענות', icon: '⭐' },
  affidavit: { label: 'תצהיר', icon: '⭐' },
  summation: { label: 'סיכומים', icon: '⭐' },
  motion: { label: 'בקשה', icon: '📎' },
  supporting: { label: 'נספח', icon: '📄' },
};

/* ─── Sources Side Panel ─── */
const SourcesPanel: React.FC<{
  notebookId: string;
  documents: Document[];
  onRefresh: () => void;
}> = ({ notebookId, documents, onRefresh }) => {
  const [isDragging, setIsDragging] = useState(false);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length === 0) return;
      try {
        await documentsApi.upload(notebookId, files, []);
        onRefresh();
      } catch {
        // silently fail
      }
    },
    [notebookId, onRefresh]
  );

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      if (files.length === 0) return;
      try {
        await documentsApi.upload(notebookId, files, []);
        onRefresh();
      } catch {
        // silently fail
      }
      e.target.value = '';
    },
    [notebookId, onRefresh]
  );

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="p-3 border-b border-slate-100">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-bold text-slate-800">מקורות</h3>
          <span className="text-[10px] text-slate-400">{documents.length}</span>
        </div>

        {/* Upload area */}
        <label
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={cn(
            'flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-dashed cursor-pointer transition-colors text-xs',
            isDragging
              ? 'border-primary-400 bg-primary-50 text-primary-600'
              : 'border-slate-200 text-slate-400 hover:border-slate-300 hover:text-slate-500'
          )}
        >
          <Upload className="w-3.5 h-3.5" />
          <span>העלאת קבצים</span>
          <input type="file" multiple className="hidden" onChange={handleFileSelect} accept=".pdf,.doc,.docx,.txt" />
        </label>
      </div>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {documents.length === 0 ? (
          <div className="text-center py-6 text-slate-400">
            <FileText className="w-6 h-6 mx-auto mb-1 opacity-40" />
            <p className="text-[11px]">אין מסמכים עדיין</p>
            <p className="text-[10px] mt-0.5">גררו קבצים או לחצו להעלאה</p>
          </div>
        ) : (
          documents.map((doc) => {
            const cls = DOC_CLASS_LABELS[doc.doc_class || 'supporting'] || DOC_CLASS_LABELS.supporting;
            return (
              <div
                key={doc.id}
                className="flex items-start gap-2 px-2.5 py-2 rounded-lg hover:bg-slate-50 transition-colors group"
              >
                <span className="text-xs mt-0.5 flex-shrink-0">{cls.icon}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-slate-700 truncate">{doc.doc_name}</p>
                  <p className="text-[10px] text-slate-400">{cls.label}</p>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Add source button */}
      <div className="p-2 border-t border-slate-100">
        <label className="flex items-center justify-center gap-1.5 w-full px-3 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-50 cursor-pointer transition-colors">
          <Plus className="w-3.5 h-3.5" />
          הוסף מקור
          <input type="file" multiple className="hidden" onChange={handleFileSelect} accept=".pdf,.doc,.docx,.txt" />
        </label>
      </div>
    </div>
  );
};

/* ─── Notes/Studio Side Panel ─── */
const StudioPanel: React.FC<{ notebookId: string }> = () => {
  const [notes, setNotes] = useState<{ id: string; text: string; ts: Date }[]>([]);
  const [draft, setDraft] = useState('');

  const addNote = () => {
    if (!draft.trim()) return;
    setNotes((prev) => [
      { id: crypto.randomUUID(), text: draft.trim(), ts: new Date() },
      ...prev,
    ]);
    setDraft('');
  };

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="p-3 border-b border-slate-100">
        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-1.5">
          <StickyNote className="w-4 h-4 text-slate-400" />
          סטודיו
        </h3>
      </div>

      {/* Quick note input */}
      <div className="p-2 border-b border-slate-50">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) addNote();
          }}
          placeholder="הערה מהירה..."
          className="w-full bg-slate-50 border border-slate-100 rounded-lg px-3 py-2 text-xs text-slate-700 placeholder-slate-400 focus:outline-none focus:border-slate-300 resize-none"
          rows={2}
        />
        <button
          onClick={addNote}
          disabled={!draft.trim()}
          className="mt-1 w-full text-[11px] text-slate-500 hover:text-slate-700 disabled:opacity-30 py-1"
        >
          Ctrl+Enter לשמירה
        </button>
      </div>

      {/* Notes list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {notes.length === 0 ? (
          <div className="text-center py-6 text-slate-400">
            <Star className="w-5 h-5 mx-auto mb-1 opacity-30" />
            <p className="text-[11px]">רשמו הערות, תובנות ותזכורות</p>
          </div>
        ) : (
          notes.map((n) => (
            <div key={n.id} className="bg-slate-50 rounded-lg px-3 py-2">
              <p className="text-xs text-slate-700 whitespace-pre-wrap">{n.text}</p>
              <p className="text-[10px] text-slate-400 mt-1">
                {n.ts.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

/* ─── Main NotebookLayout ─── */
export const NotebookLayout: React.FC = () => {
  const { notebookId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [notebook, setNotebook] = useState<Case | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showSources, setShowSources] = useState(true);
  const [showStudio, setShowStudio] = useState(true);

  useEffect(() => {
    if (!notebookId) return;
    const fetch = async () => {
      setIsLoading(true);
      try {
        const data = await casesApi.get(notebookId);
        setNotebook(data);
      } catch {
        navigate('/notebooks');
      } finally {
        setIsLoading(false);
      }
    };
    fetch();
  }, [notebookId, navigate]);

  const fetchDocuments = useCallback(async () => {
    if (!notebookId) return;
    try {
      const docs = await documentsApi.list(notebookId);
      setDocuments(docs);
    } catch {
      // silently fail
    }
  }, [notebookId]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Determine active tab from URL
  const pathSegments = location.pathname.split('/');
  const activeTab = pathSegments[3] || 'findings';

  // Redirect to default tab if on bare notebook path
  useEffect(() => {
    if (notebookId && pathSegments.length === 3) {
      navigate(`/notebooks/${notebookId}/findings`, { replace: true });
    }
  }, [notebookId, pathSegments.length, navigate]);

  const handleRunAnalysis = async () => {
    if (!notebookId || isAnalyzing) return;
    setIsAnalyzing(true);
    try {
      await casesApi.analyze(notebookId);
      const data = await casesApi.get(notebookId);
      setNotebook(data);
      navigate(`/notebooks/${notebookId}/findings`);
    } catch {
      // Error handling
    } finally {
      setIsAnalyzing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!notebook) return null;

  return (
    <div className="h-full flex flex-col">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-3">
          {/* Panel toggle buttons */}
          <button
            onClick={() => setShowSources(!showSources)}
            className={cn(
              'p-1.5 rounded-md transition-colors',
              showSources ? 'text-slate-700 bg-slate-100' : 'text-slate-400 hover:text-slate-600'
            )}
            title="מקורות"
          >
            <PanelRightClose className="w-4 h-4" />
          </button>

          <div>
            <h1 className="text-base font-bold text-slate-900">{notebook.name}</h1>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              {notebook.case_number && <span>תיק {notebook.case_number}</span>}
              {notebook.client_name && <span>{notebook.client_name}</span>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRunAnalysis}
            disabled={isAnalyzing}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              isAnalyzing
                ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                : 'bg-slate-900 text-white hover:bg-slate-800'
            )}
          >
            {isAnalyzing ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                מנתח...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                הרץ ניתוח
              </>
            )}
          </button>

          <button
            onClick={() => setShowStudio(!showStudio)}
            className={cn(
              'p-1.5 rounded-md transition-colors',
              showStudio ? 'text-slate-700 bg-slate-100' : 'text-slate-400 hover:text-slate-600'
            )}
            title="סטודיו"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 3-panel body */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT PANEL: Sources */}
        {showSources && (
          <div className="w-56 flex-shrink-0 border-l border-slate-200 overflow-hidden">
            <SourcesPanel
              notebookId={notebookId!}
              documents={documents}
              onRefresh={fetchDocuments}
            />
          </div>
        )}

        {/* CENTER: Tab bar + content */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Tab bar */}
          <div className="bg-white border-b border-slate-100 px-3">
            <nav className="flex gap-0 -mb-px">
              {CENTER_TABS.map((tab) => {
                const isActive = activeTab === tab.path;
                return (
                  <NavLink
                    key={tab.id}
                    to={`/notebooks/${notebookId}/${tab.path}`}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors',
                      isActive
                        ? 'border-slate-900 text-slate-900'
                        : 'border-transparent text-slate-400 hover:text-slate-600'
                    )}
                  >
                    <tab.icon className="w-3.5 h-3.5" />
                    {tab.label}
                  </NavLink>
                );
              })}
            </nav>
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-auto bg-slate-50/50">
            <Outlet context={{ notebook, setNotebook, isAnalyzing }} />
          </div>
        </div>

        {/* RIGHT PANEL: Studio/Notes */}
        {showStudio && (
          <div className="w-56 flex-shrink-0 border-r border-slate-200 overflow-hidden">
            <StudioPanel notebookId={notebookId!} />
          </div>
        )}
      </div>
    </div>
  );
};

export default NotebookLayout;
