import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  BookOpen,
  Plus,
  FileText,
  AlertTriangle,
  Clock,
  Search,
  Filter,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { casesApi, statsApi } from '../../api';
import type { StatsOverview } from '../../api';
import { Card, Button, Badge, Spinner, EmptyState } from '../../components/ui';
import type { Case } from '../../types';

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
};
const item = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } };

export const NotebooksListPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [notebooks, setNotebooks] = useState<Case[]>([]);
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'closed'>('all');

  useEffect(() => {
    const fetch = async () => {
      setIsLoading(true);
      try {
        const [cases, s] = await Promise.all([
          casesApi.listMyCases(),
          statsApi.overview().catch(() => null),
        ]);
        setNotebooks(cases);
        setStats(s);
      } catch {
        // Keep empty
      } finally {
        setIsLoading(false);
      }
    };
    fetch();
  }, []);

  const filtered = notebooks.filter((nb) => {
    if (filterStatus === 'active' && nb.status === 'closed') return false;
    if (filterStatus === 'closed' && nb.status !== 'closed') return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        nb.name.toLowerCase().includes(q) ||
        nb.client_name?.toLowerCase().includes(q) ||
        nb.case_number?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <motion.div initial="hidden" animate="show" variants={container} className="space-y-6">
      {/* Header */}
      <motion.div variants={item} className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            שלום, {user?.name?.split(' ')[0] || 'משתמש'}
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            {stats?.cases_active ?? notebooks.length} מחברות פעילות
            {stats?.contradictions_total ? ` · ${stats.contradictions_total} סתירות` : ''}
          </p>
        </div>
        <Button
          onClick={() => navigate('/notebooks/new')}
          leftIcon={<Plus className="w-5 h-5" />}
        >
          מחברת חדשה
        </Button>
      </motion.div>

      {/* Search + Filter */}
      <motion.div variants={item} className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="חיפוש מחברות..."
            className="w-full bg-white border border-slate-200 rounded-lg pr-9 pl-3 py-2 text-sm focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-400"
          />
        </div>
        <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1">
          {(['all', 'active', 'closed'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilterStatus(f)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                filterStatus === f
                  ? 'bg-primary-100 text-primary-700'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {f === 'all' ? 'הכל' : f === 'active' ? 'פעילות' : 'ארכיון'}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Notebooks Grid */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="w-16 h-16" />}
          title="אין מחברות עדיין"
          description="צרו את המחברת הראשונה שלכם כדי להתחיל לנתח סתירות"
          action={{
            label: 'מחברת חדשה',
            onClick: () => navigate('/notebooks/new'),
            icon: <Plus className="w-5 h-5" />,
          }}
        />
      ) : (
        <motion.div
          variants={container}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {filtered.map((nb) => (
            <motion.div key={nb.id} variants={item} whileHover={{ y: -3 }} whileTap={{ scale: 0.98 }}>
              <Card
                variant="interactive"
                padding="none"
                onClick={() => navigate(`/notebooks/${nb.id}`)}
              >
                <div className="p-5">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center">
                        <BookOpen className="w-4 h-4 text-primary-600" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-bold text-slate-900 truncate">{nb.name}</h3>
                        {nb.client_name && (
                          <p className="text-xs text-slate-500 truncate">{nb.client_name}</p>
                        )}
                      </div>
                    </div>
                    <Badge variant={nb.status === 'closed' ? 'neutral' : 'success'}>
                      {nb.status === 'closed' ? 'סגור' : 'פעיל'}
                    </Badge>
                  </div>

                  {/* Stats row */}
                  <div className="flex items-center gap-4 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <FileText className="w-3.5 h-3.5" />
                      {nb.document_count || 0} מסמכים
                    </span>
                    {(nb as Case & { contradictions_count?: number }).contradictions_count ? (
                      <span className="flex items-center gap-1 text-warning-600">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {(nb as Case & { contradictions_count?: number }).contradictions_count} סתירות
                      </span>
                    ) : null}
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {new Date(nb.created_at).toLocaleDateString('he-IL')}
                    </span>
                  </div>

                  {/* Case number */}
                  {nb.case_number && (
                    <div className="mt-3 pt-3 border-t border-slate-100">
                      <span className="text-[11px] text-slate-400">מס' תיק: {nb.case_number}</span>
                    </div>
                  )}
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
};

export default NotebooksListPage;
