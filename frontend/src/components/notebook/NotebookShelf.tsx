import React, { useEffect, useState } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  BookOpen,
  Plus,
  Search,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  FileText,
  Scale,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { casesApi } from '../../api';
import { cn } from '../../utils/cn';
import type { Case } from '../../types';

interface NotebookShelfProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export const NotebookShelf: React.FC<NotebookShelfProps> = ({ isCollapsed, onToggle }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { notebookId } = useParams();
  const [notebooks, setNotebooks] = useState<Case[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchNotebooks = async () => {
      try {
        const cases = await casesApi.listMyCases();
        setNotebooks(cases);
      } catch {
        // Silently fail — shelf will show empty
      } finally {
        setIsLoading(false);
      }
    };
    fetchNotebooks();
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const filtered = searchQuery
    ? notebooks.filter(
        (n) =>
          n.name.includes(searchQuery) ||
          n.client_name?.includes(searchQuery) ||
          n.case_number?.includes(searchQuery)
      )
    : notebooks;

  const activeNotebooks = filtered.filter((n) => n.status !== 'closed');
  const closedNotebooks = filtered.filter((n) => n.status === 'closed');

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 72 : 280 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="fixed right-0 top-0 h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white shadow-2xl z-50 flex flex-col"
    >
      {/* Logo */}
      <div className="p-4 border-b border-slate-700/50">
        <NavLink to="/notebooks" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center flex-shrink-0">
            <Scale className="w-6 h-6 text-white" />
          </div>
          {!isCollapsed && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <h1 className="text-lg font-bold">Jethro</h1>
              <p className="text-[11px] text-slate-400">המחברת המשפטית</p>
            </motion.div>
          )}
        </NavLink>
      </div>

      {/* New Notebook */}
      {!isCollapsed ? (
        <div className="p-3">
          <button
            onClick={() => navigate('/notebooks/new')}
            className="w-full flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary-600 hover:bg-primary-500 transition-colors text-sm font-medium"
          >
            <Plus className="w-4 h-4" />
            מחברת חדשה
          </button>
        </div>
      ) : (
        <div className="p-2 flex justify-center">
          <button
            onClick={() => navigate('/notebooks/new')}
            className="w-10 h-10 rounded-xl bg-primary-600 hover:bg-primary-500 flex items-center justify-center transition-colors"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>
      )}

      {/* Search */}
      {!isCollapsed && (
        <div className="px-3 pb-2">
          <div className="relative">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="חיפוש מחברות..."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg pr-9 pl-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary-500"
            />
          </div>
        </div>
      )}

      {/* Notebooks list */}
      <nav className="flex-1 overflow-y-auto custom-scrollbar px-2 py-1 space-y-0.5">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-5 h-5 border-2 border-slate-600 border-t-primary-400 rounded-full animate-spin" />
          </div>
        ) : activeNotebooks.length === 0 ? (
          !isCollapsed && (
            <div className="text-center py-8 text-slate-500 text-sm">
              <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>אין מחברות עדיין</p>
            </div>
          )
        ) : (
          <>
            {activeNotebooks.map((nb) => (
              <NavLink
                key={nb.id}
                to={`/notebooks/${nb.id}`}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-all duration-150 group',
                    'hover:bg-white/10',
                    isActive || nb.id === notebookId
                      ? 'bg-primary-600/20 text-white border-r-3 border-primary-400'
                      : 'text-slate-400'
                  )
                }
              >
                <BookOpen className="w-4 h-4 flex-shrink-0" />
                {!isCollapsed && (
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{nb.name}</p>
                    <div className="flex items-center gap-2 text-[11px] text-slate-500">
                      <span className="flex items-center gap-0.5">
                        <FileText className="w-3 h-3" />
                        {nb.document_count || 0}
                      </span>
                      {(nb as Case & { contradictions_count?: number }).contradictions_count ? (
                        <span className="flex items-center gap-0.5 text-warning-400">
                          <AlertTriangle className="w-3 h-3" />
                          {(nb as Case & { contradictions_count?: number }).contradictions_count}
                        </span>
                      ) : null}
                    </div>
                  </div>
                )}
              </NavLink>
            ))}

            {closedNotebooks.length > 0 && !isCollapsed && (
              <div className="pt-3 mt-2 border-t border-slate-700/50">
                <p className="px-3 text-[11px] text-slate-500 mb-1">ארכיון</p>
                {closedNotebooks.map((nb) => (
                  <NavLink
                    key={nb.id}
                    to={`/notebooks/${nb.id}`}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-slate-500 hover:bg-white/5 text-sm"
                  >
                    <BookOpen className="w-4 h-4 opacity-50" />
                    <span className="truncate">{nb.name}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </>
        )}
      </nav>

      {/* Bottom: settings + user */}
      <div className="border-t border-slate-700/50">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 px-4 py-3 transition-colors',
              'hover:bg-white/5',
              isActive ? 'text-white' : 'text-slate-400',
              isCollapsed && 'justify-center'
            )
          }
        >
          <Settings className="w-4 h-4" />
          {!isCollapsed && <span className="text-sm">הגדרות</span>}
        </NavLink>

        {user && (
          <div className={cn('flex items-center gap-2.5 px-4 py-3', isCollapsed && 'justify-center')}>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-400 to-accent-500 flex items-center justify-center flex-shrink-0">
              <span className="text-white text-sm font-bold">
                {user.name?.charAt(0) || user.email.charAt(0).toUpperCase()}
              </span>
            </div>
            {!isCollapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{user.name || user.email}</p>
                <p className="text-[11px] text-slate-400 truncate">{user.firm_name}</p>
              </div>
            )}
          </div>
        )}

        <button
          onClick={handleLogout}
          className={cn(
            'flex items-center gap-2.5 w-full px-4 py-2.5 text-slate-400 hover:text-white hover:bg-danger-600/20 transition-colors',
            isCollapsed && 'justify-center'
          )}
        >
          <LogOut className="w-4 h-4" />
          {!isCollapsed && <span className="text-sm">התנתק</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-12 bg-slate-800 rounded-l-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
      >
        {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>
    </motion.aside>
  );
};

export default NotebookShelf;
