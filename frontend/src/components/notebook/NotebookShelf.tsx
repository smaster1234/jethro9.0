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
  FileText,
  Scale,
  Coins,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { casesApi, creditsApi } from '../../api';
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
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchNotebooks = async () => {
      try {
        const cases = await casesApi.listMyCases();
        setNotebooks(cases);
      } catch {
        // Silently fail
      } finally {
        setIsLoading(false);
      }
    };
    fetchNotebooks();
  }, []);

  // Fetch credit balance
  useEffect(() => {
    const fetchCredits = async () => {
      try {
        const info = await creditsApi.getMyCredits();
        setCreditBalance(info.balance);
      } catch {
        // Silently fail — credits display is non-critical
      }
    };
    fetchCredits();
    // Refresh every 60 seconds
    const interval = setInterval(fetchCredits, 60_000);
    return () => clearInterval(interval);
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
      animate={{ width: isCollapsed ? 64 : 260 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="fixed right-0 top-0 h-screen bg-white border-l border-slate-200 z-50 flex flex-col"
    >
      {/* Logo */}
      <div className="p-3 border-b border-slate-100">
        <NavLink to="/notebooks" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-slate-900 flex items-center justify-center flex-shrink-0">
            <Scale className="w-5 h-5 text-white" />
          </div>
          {!isCollapsed && (
            <div>
              <h1 className="text-base font-bold text-slate-900">Jethro</h1>
              <p className="text-[10px] text-slate-400 leading-none">המחברת המשפטית</p>
            </div>
          )}
        </NavLink>
      </div>

      {/* New notebook button */}
      <div className={cn('p-2', isCollapsed && 'flex justify-center')}>
        {!isCollapsed ? (
          <button
            onClick={() => navigate('/notebooks/new')}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors text-sm"
          >
            <Plus className="w-4 h-4" />
            מחברת חדשה
          </button>
        ) : (
          <button
            onClick={() => navigate('/notebooks/new')}
            className="w-9 h-9 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-50 transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Search */}
      {!isCollapsed && (
        <div className="px-2 pb-2">
          <div className="relative">
            <Search className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="חיפוש..."
              className="w-full bg-slate-50 border border-slate-100 rounded-lg pr-8 pl-3 py-1.5 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:border-slate-300 focus:bg-white"
            />
          </div>
        </div>
      )}

      {/* Notebooks list */}
      <nav className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-4 h-4 border-2 border-slate-200 border-t-slate-500 rounded-full animate-spin" />
          </div>
        ) : activeNotebooks.length === 0 ? (
          !isCollapsed && (
            <div className="text-center py-8 text-slate-400 text-xs">
              <BookOpen className="w-6 h-6 mx-auto mb-1.5 opacity-40" />
              <p>אין מחברות</p>
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
                    'flex items-center gap-2 px-2.5 py-2 rounded-lg transition-colors text-sm',
                    isActive || nb.id === notebookId
                      ? 'bg-slate-100 text-slate-900 font-medium'
                      : 'text-slate-600 hover:bg-slate-50'
                  )
                }
              >
                <BookOpen className="w-4 h-4 flex-shrink-0 text-slate-400" />
                {!isCollapsed && (
                  <div className="flex-1 min-w-0">
                    <p className="truncate">{nb.name}</p>
                    <p className="text-[10px] text-slate-400 flex items-center gap-1.5">
                      <FileText className="w-3 h-3 inline" />
                      {nb.document_count || 0} מסמכים
                    </p>
                  </div>
                )}
              </NavLink>
            ))}

            {closedNotebooks.length > 0 && !isCollapsed && (
              <div className="pt-2 mt-2 border-t border-slate-100">
                <p className="px-2.5 text-[10px] text-slate-400 mb-1">ארכיון</p>
                {closedNotebooks.map((nb) => (
                  <NavLink
                    key={nb.id}
                    to={`/notebooks/${nb.id}`}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-slate-400 hover:bg-slate-50 text-xs"
                  >
                    <BookOpen className="w-3.5 h-3.5 opacity-40" />
                    <span className="truncate">{nb.name}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </>
        )}
      </nav>

      {/* Bottom */}
      <div className="border-t border-slate-100 py-1">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2 px-3 py-2 text-sm transition-colors',
              'hover:bg-slate-50',
              isActive ? 'text-slate-900' : 'text-slate-500',
              isCollapsed && 'justify-center'
            )
          }
        >
          <Settings className="w-4 h-4" />
          {!isCollapsed && <span>הגדרות</span>}
        </NavLink>

        {/* Credit balance */}
        {creditBalance !== null && (
          <div
            className={cn(
              'flex items-center gap-2 px-3 py-2 mx-2 mb-1 rounded-lg',
              creditBalance > 20 ? 'bg-emerald-50' : creditBalance > 0 ? 'bg-amber-50' : 'bg-red-50',
              isCollapsed && 'justify-center mx-1 px-1'
            )}
          >
            <Coins className={cn(
              'w-4 h-4 flex-shrink-0',
              creditBalance > 20 ? 'text-emerald-500' : creditBalance > 0 ? 'text-amber-500' : 'text-red-500'
            )} />
            {!isCollapsed && (
              <div className="flex-1 min-w-0">
                <p className={cn(
                  'text-xs font-semibold',
                  creditBalance > 20 ? 'text-emerald-700' : creditBalance > 0 ? 'text-amber-700' : 'text-red-700'
                )}>
                  {creditBalance} <span className="font-normal">קרדיטים</span>
                </p>
              </div>
            )}
          </div>
        )}

        {user && !isCollapsed && (
          <div className="flex items-center gap-2 px-3 py-2">
            <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0">
              <span className="text-slate-600 text-xs font-medium">
                {user.name?.charAt(0) || user.email.charAt(0).toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-slate-700 truncate">{user.name || user.email}</p>
              <p className="text-[10px] text-slate-400 truncate">{user.firm_name}</p>
            </div>
          </div>
        )}

        <button
          onClick={handleLogout}
          className={cn(
            'flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors',
            isCollapsed && 'justify-center'
          )}
        >
          <LogOut className="w-4 h-4" />
          {!isCollapsed && <span>יציאה</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 bg-white border border-slate-200 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-600 transition-colors shadow-sm"
      >
        {isCollapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>
    </motion.aside>
  );
};

export default NotebookShelf;
