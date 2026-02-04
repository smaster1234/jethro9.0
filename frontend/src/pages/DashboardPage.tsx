import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Briefcase,
  FileText,
  AlertTriangle,
  TrendingUp,
  Plus,
  ArrowLeft,
  Clock,
  CheckCircle,
  Search,
  Target,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { casesApi, healthApi, statsApi } from '../api';
import type { StatsOverview } from '../api';
import { Card, Button, Badge, EmptyState, Spinner } from '../components/ui';
import type { Case, HealthResponse } from '../types';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  trend?: string;
  color: 'primary' | 'success' | 'warning' | 'danger' | 'accent';
}

const StatCard: React.FC<StatCardProps> = ({ icon, label, value, trend, color }) => {
  const colorClasses = {
    primary: 'from-primary-500 to-primary-600',
    success: 'from-success-500 to-green-600',
    warning: 'from-warning-500 to-orange-600',
    danger: 'from-danger-500 to-red-600',
    accent: 'from-accent-500 to-accent-600',
  };

  return (
    <motion.div variants={item}>
      <Card className="relative overflow-hidden">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-slate-500 mb-1">{label}</p>
            <p className="text-3xl font-bold text-slate-900">{value}</p>
            {trend && (
              <div className="flex items-center gap-1 mt-2 text-success-600 text-sm">
                <TrendingUp className="w-4 h-4" />
                <span>{trend}</span>
              </div>
            )}
          </div>
          <div
            className={`w-12 h-12 rounded-xl bg-gradient-to-br ${colorClasses[color]} flex items-center justify-center text-white shadow-lg`}
          >
            {icon}
          </div>
        </div>
        <div
          className={`absolute bottom-0 right-0 w-32 h-32 bg-gradient-to-tl ${colorClasses[color]} opacity-5 rounded-full -mb-16 -mr-16`}
        />
      </Card>
    </motion.div>
  );
};

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [cases, setCases] = useState<Case[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const fetchData = async () => {
    setIsLoading(true);
    setLoadError('');
    try {
      const [casesData, healthData, statsData] = await Promise.all([
        casesApi.listMyCases(),
        healthApi.check(),
        statsApi.overview().catch(() => null),
      ]);
      setCases(casesData);
      setHealth(healthData);
      setStats(statsData);
    } catch (error) {
      console.error('Failed to fetch data:', error);
      setLoadError('לא ניתן להתחבר לשרת. ודא שהשרת פועל ונסה שוב.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const activeCases = stats?.cases_active ?? cases.filter((c) => c.status !== 'closed').length;
  const totalDocs = stats?.documents_total ?? cases.reduce((acc, c) => acc + (c.document_count || 0), 0);
  const totalContradictions = stats?.contradictions_total ?? 0;
  const analysisRunsTotal = stats?.analysis_runs_total ?? 0;

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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Card className="max-w-md text-center">
          <div className="w-16 h-16 rounded-full bg-danger-100 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-danger-600" />
          </div>
          <h2 className="text-xl font-bold text-slate-900 mb-2">שגיאת חיבור</h2>
          <p className="text-slate-600 mb-4">{loadError}</p>
          <Button onClick={fetchData}>נסה שוב</Button>
        </Card>
      </div>
    );
  }

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={container}
      className="space-y-8"
    >
      {/* Header */}
      <motion.div variants={item} className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            שלום, {user?.name?.split(' ')[0] || 'משתמש'} 👋
          </h1>
          <p className="text-slate-500 mt-1">
            הנה סיכום הפעילות שלך ב-{user?.firm_name || 'המשרד'}
          </p>
        </div>
        <Button onClick={() => navigate('/cases/new')} leftIcon={<Plus className="w-5 h-5" />}>
          תיק חדש
        </Button>
      </motion.div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <StatCard
          icon={<Briefcase className="w-6 h-6" />}
          label="תיקים פעילים"
          value={activeCases}
          color="primary"
        />
        <StatCard
          icon={<FileText className="w-6 h-6" />}
          label="מסמכים"
          value={totalDocs}
          color="accent"
        />
        <StatCard
          icon={<AlertTriangle className="w-6 h-6" />}
          label="סתירות שזוהו"
          value={totalContradictions}
          color="warning"
        />
        <StatCard
          icon={<Target className="w-6 h-6" />}
          label="ריצות ניתוח"
          value={analysisRunsTotal}
          color="danger"
        />
        <StatCard
          icon={<CheckCircle className="w-6 h-6" />}
          label="מצב המערכת"
          value={health?.status === 'ok' ? 'תקין' : 'בעיה'}
          color={health?.status === 'ok' ? 'success' : 'danger'}
        />
      </div>

      {/* Quick Actions */}
      <motion.div variants={item}>
        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-4">פעולות מהירות</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Button
              variant="secondary"
              className="justify-start h-auto py-4"
              onClick={() => navigate('/analyze')}
              leftIcon={<Search className="w-5 h-5 text-primary-500" />}
            >
              <div className="text-right">
                <div className="font-semibold">ניתוח טקסט</div>
                <div className="text-xs text-slate-500">הדבק טקסט ונתח סתירות</div>
              </div>
            </Button>
            <Button
              variant="secondary"
              className="justify-start h-auto py-4"
              onClick={() => navigate('/cases')}
              leftIcon={<Briefcase className="w-5 h-5 text-accent-500" />}
            >
              <div className="text-right">
                <div className="font-semibold">ניהול תיקים</div>
                <div className="text-xs text-slate-500">צפה וערוך תיקים</div>
              </div>
            </Button>
            <Button
              variant="secondary"
              className="justify-start h-auto py-4"
              onClick={() => navigate('/cases/new')}
              leftIcon={<Plus className="w-5 h-5 text-success-500" />}
            >
              <div className="text-right">
                <div className="font-semibold">תיק חדש</div>
                <div className="text-xs text-slate-500">צור תיק והעלה מסמכים</div>
              </div>
            </Button>
          </div>
        </Card>
      </motion.div>

      {/* Recent Cases */}
      <motion.div variants={item}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-900">תיקים אחרונים</h2>
          <Link
            to="/cases"
            className="text-primary-600 hover:text-primary-700 text-sm font-medium flex items-center gap-1"
          >
            צפה בכל התיקים
            <ArrowLeft className="w-4 h-4" />
          </Link>
        </div>

        {cases.length === 0 ? (
          <EmptyState
            icon={<Briefcase className="w-16 h-16" />}
            title="אין תיקים עדיין"
            description="צרו את התיק הראשון שלכם כדי להתחיל לעבוד"
            action={{
              label: 'צור תיק חדש',
              onClick: () => navigate('/cases/new'),
              icon: <Plus className="w-5 h-5" />,
            }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {cases.slice(0, 6).map((caseItem) => (
              <motion.div
                key={caseItem.id}
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
                        <h3 className="font-bold text-slate-900 truncate">
                          {caseItem.name}
                        </h3>
                        <p className="text-sm text-slate-500 truncate">
                          {caseItem.client_name}
                        </p>
                      </div>
                      {getStatusBadge(caseItem.status)}
                    </div>

                    <div className="flex items-center gap-4 text-sm text-slate-500">
                      <div className="flex items-center gap-1">
                        <FileText className="w-4 h-4" />
                        <span>{caseItem.document_count || 0} מסמכים</span>
                      </div>
                      {(caseItem as Case & { contradictions_count?: number }).contradictions_count ? (
                        <div className="flex items-center gap-1 text-warning-600">
                          <AlertTriangle className="w-4 h-4" />
                          <span>{(caseItem as Case & { contradictions_count?: number }).contradictions_count} סתירות</span>
                        </div>
                      ) : null}
                      <div className="flex items-center gap-1">
                        <Clock className="w-4 h-4" />
                        <span>
                          {new Date(caseItem.created_at).toLocaleDateString('he-IL')}
                        </span>
                      </div>
                    </div>

                    {caseItem.case_number && (
                      <div className="mt-3 pt-3 border-t border-slate-100">
                        <span className="text-xs text-slate-400">
                          מס' תיק: {caseItem.case_number}
                        </span>
                      </div>
                    )}
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>

      {/* System Info */}
      {health && (
        <motion.div variants={item}>
          <Card className="bg-slate-50">
            <div className="flex items-center gap-4 text-sm text-slate-500">
              <div className="flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${
                    health.status === 'ok' ? 'bg-success-500' : 'bg-danger-500'
                  }`}
                />
                <span>מצב: {health.status === 'ok' ? 'תקין' : 'בעיה'}</span>
              </div>
              <div className="border-r border-slate-300 h-4" />
              <span>מצב LLM: {health.llm_mode || 'לא מוגדר'}</span>
              {health.version && (
                <>
                  <div className="border-r border-slate-300 h-4" />
                  <span>גרסה: {health.version}</span>
                </>
              )}
            </div>
          </Card>
        </motion.div>
      )}
    </motion.div>
  );
};

export default DashboardPage;
