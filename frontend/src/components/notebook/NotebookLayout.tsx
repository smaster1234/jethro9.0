import React, { useEffect, useState } from 'react';
import { Outlet, useParams, useNavigate, NavLink, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  FileText,
  AlertTriangle,
  Target,
  Users,
  StickyNote,
  Clock,
  Play,
  Loader2,
} from 'lucide-react';
import { casesApi } from '../../api';
import { Spinner } from '../ui';
import { cn } from '../../utils/cn';
import type { Case } from '../../types';

const NOTEBOOK_TABS = [
  { id: 'sources', label: 'מקורות', icon: FileText, path: 'sources' },
  { id: 'timeline', label: 'ציר זמן', icon: Clock, path: 'timeline' },
  { id: 'findings', label: 'ממצאים', icon: AlertTriangle, path: 'findings' },
  { id: 'crossexam', label: 'חקירה', icon: Target, path: 'crossexam' },
  { id: 'witnesses', label: 'עדים', icon: Users, path: 'witnesses' },
  { id: 'notes', label: 'הערות', icon: StickyNote, path: 'notes' },
] as const;

export const NotebookLayout: React.FC = () => {
  const { notebookId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [notebook, setNotebook] = useState<Case | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

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
      // Refresh the notebook and navigate to findings
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
      {/* Notebook header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-white/80 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900">{notebook.name}</h1>
            <div className="flex items-center gap-3 text-sm text-slate-500 mt-0.5">
              {notebook.case_number && <span>תיק {notebook.case_number}</span>}
              {notebook.client_name && <span>{notebook.client_name}</span>}
              {notebook.court && <span>{notebook.court}</span>}
            </div>
          </div>
        </div>

        <button
          onClick={handleRunAnalysis}
          disabled={isAnalyzing}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            isAnalyzing
              ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
              : 'bg-primary-600 text-white hover:bg-primary-700'
          )}
        >
          {isAnalyzing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              מנתח...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              הרץ ניתוח
            </>
          )}
        </button>
      </div>

      {/* Tab bar — styled as notebook dividers */}
      <div className="bg-white border-b border-slate-200 px-4">
        <nav className="flex gap-0 -mb-px">
          {NOTEBOOK_TABS.map((tab) => {
            const isActive = activeTab === tab.path;
            return (
              <NavLink
                key={tab.id}
                to={`/notebooks/${notebookId}/${tab.path}`}
                className={cn(
                  'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                  isActive
                    ? 'border-primary-500 text-primary-700 bg-primary-50/50'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                )}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        <Outlet context={{ notebook, setNotebook, isAnalyzing }} />
      </div>
    </div>
  );
};

export default NotebookLayout;
