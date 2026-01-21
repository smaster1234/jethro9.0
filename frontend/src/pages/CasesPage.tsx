import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Briefcase,
  Plus,
  Search,
  FileText,
  Clock,
  Grid,
  List,
  ChevronDown,
} from 'lucide-react';
import { casesApi, handleApiError } from '../api';
import { Card, Button, Badge, EmptyState, Spinner, Input, Modal } from '../components/ui';
import type { Case, CreateCaseRequest } from '../types';

type ViewMode = 'grid' | 'list';
type StatusFilter = 'all' | 'active' | 'pending' | 'closed';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

export const CasesPage: React.FC = () => {
  const navigate = useNavigate();
  const [cases, setCases] = useState<Case[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [showNewCaseModal, setShowNewCaseModal] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  // New case form state
  const [newCase, setNewCase] = useState<CreateCaseRequest>({
    name: '',
    client_name: '',
    our_side: 'plaintiff',
    opponent_name: '',
    court: '',
    case_number: '',
    description: '',
  });

  useEffect(() => {
    fetchCases();
  }, []);

  const fetchCases = async () => {
    try {
      const data = await casesApi.listMyCases();
      setCases(data);
    } catch (error) {
      console.error('Failed to fetch cases:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError('');
    setIsCreating(true);

    try {
      const created = await casesApi.create(newCase);
      setCases([created, ...cases]);
      setShowNewCaseModal(false);
      setNewCase({
        name: '',
        client_name: '',
        our_side: 'plaintiff',
        opponent_name: '',
        court: '',
        case_number: '',
        description: '',
      });
      navigate(`/cases/${created.id}`);
    } catch (error) {
      setCreateError(handleApiError(error));
    } finally {
      setIsCreating(false);
    }
  };

  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.client_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.case_number?.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus = statusFilter === 'all' || c.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case 'active':
        return <Badge variant="success">פעיל</Badge>;
      case 'pending':
        return <Badge variant="warning">ממתין</Badge>;
      case 'closed':
        return <Badge variant="neutral">סגור</Badge>;
      default:
        return <Badge variant="primary">חדש</Badge>;
    }
  };

  const getSideBadge = (side?: string) => {
    switch (side) {
      case 'plaintiff':
        return <Badge variant="primary" size="sm">תובע</Badge>;
      case 'defendant':
        return <Badge variant="accent" size="sm">נתבע</Badge>;
      default:
        return <Badge variant="neutral" size="sm">אחר</Badge>;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">תיקים</h1>
          <p className="text-slate-500 mt-1">ניהול התיקים המשפטיים שלך</p>
        </div>
        <Button onClick={() => setShowNewCaseModal(true)} leftIcon={<Plus className="w-5 h-5" />}>
          תיק חדש
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <Input
              placeholder="חיפוש לפי שם, לקוח או מספר תיק..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftIcon={<Search className="w-5 h-5" />}
            />
          </div>

          <div className="flex gap-2">
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                className="appearance-none pl-10 pr-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 font-medium focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none cursor-pointer"
              >
                <option value="all">כל הסטטוסים</option>
                <option value="active">פעילים</option>
                <option value="pending">ממתינים</option>
                <option value="closed">סגורים</option>
              </select>
              <ChevronDown className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400 pointer-events-none" />
            </div>

            <div className="flex rounded-xl border-2 border-slate-200 overflow-hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-3 transition-colors ${
                  viewMode === 'grid' ? 'bg-primary-50 text-primary-600' : 'text-slate-400 hover:bg-slate-50'
                }`}
              >
                <Grid className="w-5 h-5" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-3 transition-colors ${
                  viewMode === 'list' ? 'bg-primary-50 text-primary-600' : 'text-slate-400 hover:bg-slate-50'
                }`}
              >
                <List className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </Card>

      {/* Cases List */}
      {filteredCases.length === 0 ? (
        <EmptyState
          icon={<Briefcase className="w-16 h-16" />}
          title={searchQuery ? 'לא נמצאו תוצאות' : 'אין תיקים עדיין'}
          description={
            searchQuery
              ? 'נסה לחפש עם מילים אחרות'
              : 'צרו את התיק הראשון שלכם כדי להתחיל לעבוד'
          }
          action={
            !searchQuery
              ? {
                  label: 'צור תיק חדש',
                  onClick: () => setShowNewCaseModal(true),
                  icon: <Plus className="w-5 h-5" />,
                }
              : undefined
          }
        />
      ) : viewMode === 'grid' ? (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          <AnimatePresence>
            {filteredCases.map((caseItem) => (
              <motion.div
                key={caseItem.id}
                variants={item}
                layout
                whileHover={{ y: -4 }}
                whileTap={{ scale: 0.98 }}
              >
                <Card
                  variant="interactive"
                  padding="none"
                  onClick={() => navigate(`/cases/${caseItem.id}`)}
                >
                  <div className="p-5">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-slate-900 truncate">{caseItem.name}</h3>
                        <p className="text-sm text-slate-500 truncate">{caseItem.client_name}</p>
                      </div>
                      {getStatusBadge(caseItem.status)}
                    </div>

                    <div className="flex items-center gap-2 mb-3">
                      {getSideBadge(caseItem.our_side)}
                      {caseItem.court && (
                        <span className="text-xs text-slate-400">{caseItem.court}</span>
                      )}
                    </div>

                    <div className="flex items-center gap-4 text-sm text-slate-500">
                      <div className="flex items-center gap-1">
                        <FileText className="w-4 h-4" />
                        <span>{caseItem.document_count || 0} מסמכים</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Clock className="w-4 h-4" />
                        <span>{new Date(caseItem.created_at).toLocaleDateString('he-IL')}</span>
                      </div>
                    </div>

                    {caseItem.case_number && (
                      <div className="mt-3 pt-3 border-t border-slate-100">
                        <span className="text-xs text-slate-400">מס' תיק: {caseItem.case_number}</span>
                      </div>
                    )}
                  </div>
                </Card>
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      ) : (
        <Card padding="none">
          <div className="divide-y divide-slate-100">
            {filteredCases.map((caseItem) => (
              <motion.div
                key={caseItem.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="p-4 hover:bg-slate-50 cursor-pointer transition-colors"
                onClick={() => navigate(`/cases/${caseItem.id}`)}
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-primary-100 flex items-center justify-center flex-shrink-0">
                    <Briefcase className="w-6 h-6 text-primary-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-slate-900">{caseItem.name}</h3>
                      {getStatusBadge(caseItem.status)}
                      {getSideBadge(caseItem.our_side)}
                    </div>
                    <p className="text-sm text-slate-500">
                      {caseItem.client_name}
                      {caseItem.case_number && ` • מס' ${caseItem.case_number}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-6 text-sm text-slate-500">
                    <div className="flex items-center gap-1">
                      <FileText className="w-4 h-4" />
                      <span>{caseItem.document_count || 0}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      <span>{new Date(caseItem.created_at).toLocaleDateString('he-IL')}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </Card>
      )}

      {/* New Case Modal */}
      <Modal
        isOpen={showNewCaseModal}
        onClose={() => setShowNewCaseModal(false)}
        title="תיק חדש"
        description="מלאו את פרטי התיק כדי ליצור תיק חדש במערכת"
        size="lg"
      >
        <form onSubmit={handleCreateCase} className="space-y-5">
          {createError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {createError}
            </div>
          )}

          <Input
            label="שם התיק"
            value={newCase.name}
            onChange={(e) => setNewCase({ ...newCase, name: e.target.value })}
            placeholder="לדוגמה: תביעת פיצויים - כהן נ' ישראלי"
            required
          />

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="שם הלקוח"
              value={newCase.client_name}
              onChange={(e) => setNewCase({ ...newCase, client_name: e.target.value })}
              placeholder="שם הלקוח שלכם"
              required
            />
            <Input
              label="שם הצד השני"
              value={newCase.opponent_name}
              onChange={(e) => setNewCase({ ...newCase, opponent_name: e.target.value })}
              placeholder="שם בעל הדין הנגדי"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">צד הלקוח</label>
              <select
                value={newCase.our_side}
                onChange={(e) =>
                  setNewCase({ ...newCase, our_side: e.target.value as 'plaintiff' | 'defendant' | 'other' })
                }
                className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
              >
                <option value="plaintiff">תובע</option>
                <option value="defendant">נתבע</option>
                <option value="other">אחר</option>
              </select>
            </div>
            <Input
              label="בית משפט"
              value={newCase.court}
              onChange={(e) => setNewCase({ ...newCase, court: e.target.value })}
              placeholder="לדוגמה: שלום תל אביב"
            />
          </div>

          <Input
            label="מספר תיק בית משפט"
            value={newCase.case_number}
            onChange={(e) => setNewCase({ ...newCase, case_number: e.target.value })}
            placeholder="לדוגמה: ת״א 12345-01-24"
          />

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">תיאור (אופציונלי)</label>
            <textarea
              value={newCase.description}
              onChange={(e) => setNewCase({ ...newCase, description: e.target.value })}
              rows={3}
              className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none resize-none"
              placeholder="תיאור קצר של התיק..."
            />
          </div>

          <div className="flex gap-3 pt-4">
            <Button type="submit" className="flex-1" isLoading={isCreating}>
              צור תיק
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setShowNewCaseModal(false)}
            >
              ביטול
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default CasesPage;
