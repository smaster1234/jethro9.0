import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowRight,
  FileText,
  Upload,
  Play,
  AlertTriangle,
  CheckCircle,
  Clock,
  Trash2,
  Eye,
  Search,
  RefreshCw,
} from 'lucide-react';
import { casesApi, documentsApi, handleApiError } from '../api';
import {
  Card,
  Button,
  Badge,
  Spinner,
  EmptyState,
  Modal,
  Progress,
} from '../components/ui';
import type { Case, Document, AnalysisRun, Folder as FolderType } from '../types';

type Tab = 'documents' | 'analysis' | 'history';

export const CaseDetailPage: React.FC = () => {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();

  const [caseData, setCaseData] = useState<Case | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [_folders, setFolders] = useState<FolderType[]>([]);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('documents');

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState('');

  // Analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [_currentRun, setCurrentRun] = useState<AnalysisRun | null>(null);

  // Polling for jobs
  const [activeJobs, setActiveJobs] = useState<string[]>([]);

  useEffect(() => {
    if (caseId) {
      fetchCaseData();
    }
  }, [caseId]);

  // Poll for job status
  useEffect(() => {
    if (activeJobs.length === 0) return;

    const interval = setInterval(async () => {
      const stillActive: string[] = [];

      for (const jobId of activeJobs) {
        try {
          const job = await documentsApi.getJobStatus(jobId);
          if (job.status === 'queued' || job.status === 'started') {
            stillActive.push(jobId);
          }
        } catch {
          // Job finished or error
        }
      }

      setActiveJobs(stillActive);

      if (stillActive.length < activeJobs.length) {
        // Some jobs finished, refresh documents
        fetchDocuments();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [activeJobs, caseId]);

  const fetchCaseData = async () => {
    if (!caseId) return;

    try {
      const [caseRes, docsRes, runsRes] = await Promise.all([
        casesApi.get(caseId),
        documentsApi.list(caseId),
        casesApi.listRuns(caseId).catch(() => []),
      ]);

      setCaseData(caseRes);
      setDocuments(docsRes);
      setAnalysisRuns(runsRes);

      // Try to get folders
      try {
        const foldersRes = await documentsApi.folders.getTree(caseId);
        setFolders(foldersRes);
      } catch {
        // Folders not available
      }
    } catch (error) {
      console.error('Failed to fetch case:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchDocuments = async () => {
    if (!caseId) return;
    try {
      const docsRes = await documentsApi.list(caseId);
      setDocuments(docsRes);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    }
  };

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    setUploadFiles((prev) => [...prev, ...files]);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    setUploadFiles((prev) => [...prev, ...files]);
  };

  const handleUpload = async () => {
    if (!caseId || uploadFiles.length === 0) return;

    setIsUploading(true);
    setUploadError('');
    setUploadProgress(0);

    try {
      const metadata = uploadFiles.map((file) => ({
        name: file.name,
        party: 'unknown',
        role: 'evidence',
      }));

      const result = await documentsApi.upload(caseId, uploadFiles, metadata);

      // Track active jobs
      if (result.job_ids && result.job_ids.length > 0) {
        setActiveJobs(result.job_ids);
      }

      setUploadFiles([]);
      setShowUploadModal(false);
      await fetchDocuments();
    } catch (error) {
      setUploadError(handleApiError(error));
    } finally {
      setIsUploading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!caseId) return;

    setIsAnalyzing(true);
    setAnalysisProgress(0);

    try {
      // Simulate progress
      const progressInterval = setInterval(() => {
        setAnalysisProgress((prev) => Math.min(prev + 10, 90));
      }, 500);

      const result = await casesApi.analyze(caseId, { force: false });

      clearInterval(progressInterval);
      setAnalysisProgress(100);

      // Refresh runs
      const runs = await casesApi.listRuns(caseId);
      setAnalysisRuns(runs);

      // Navigate to analysis tab
      setActiveTab('analysis');

      if (result.run_id) {
        const run = await casesApi.getRun(result.run_id);
        setCurrentRun(run);
      }
    } catch (error) {
      console.error('Analysis failed:', error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success" icon={<CheckCircle className="w-3 h-3" />}>הושלם</Badge>;
      case 'processing':
      case 'running':
        return <Badge variant="warning" icon={<RefreshCw className="w-3 h-3 animate-spin" />}>בעיבוד</Badge>;
      case 'pending':
        return <Badge variant="neutral" icon={<Clock className="w-3 h-3" />}>ממתין</Badge>;
      case 'failed':
        return <Badge variant="danger" icon={<AlertTriangle className="w-3 h-3" />}>נכשל</Badge>;
      default:
        return <Badge variant="neutral">{status}</Badge>;
    }
  };

  const getFileIcon = (mimeType?: string) => {
    if (mimeType?.includes('pdf')) return '📄';
    if (mimeType?.includes('word') || mimeType?.includes('docx')) return '📝';
    if (mimeType?.includes('image')) return '🖼️';
    return '📁';
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!caseData) {
    return (
      <EmptyState
        icon={<AlertTriangle className="w-16 h-16" />}
        title="תיק לא נמצא"
        description="התיק המבוקש אינו קיים או שאין לך הרשאה לצפות בו"
        action={{
          label: 'חזרה לתיקים',
          onClick: () => navigate('/cases'),
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate('/cases')}
            className="flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-4 transition-colors"
          >
            <ArrowRight className="w-4 h-4" />
            חזרה לתיקים
          </button>
          <h1 className="text-3xl font-bold text-slate-900">{caseData.name}</h1>
          <div className="flex items-center gap-4 mt-2 text-slate-500">
            <span>{caseData.client_name}</span>
            {caseData.case_number && (
              <>
                <span className="text-slate-300">•</span>
                <span>מס' {caseData.case_number}</span>
              </>
            )}
            {caseData.court && (
              <>
                <span className="text-slate-300">•</span>
                <span>{caseData.court}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex gap-3">
          <Button
            variant="secondary"
            onClick={() => setShowUploadModal(true)}
            leftIcon={<Upload className="w-5 h-5" />}
          >
            העלאת מסמכים
          </Button>
          <Button
            onClick={handleAnalyze}
            isLoading={isAnalyzing}
            leftIcon={<Play className="w-5 h-5" />}
            disabled={documents.length === 0}
          >
            הפעל ניתוח
          </Button>
        </div>
      </div>

      {/* Analysis Progress */}
      {isAnalyzing && (
        <Card>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-900">מנתח מסמכים...</span>
              <span className="text-sm text-slate-500">{analysisProgress}%</span>
            </div>
            <Progress value={analysisProgress} animated />
            <p className="text-sm text-slate-500">
              מזהה סתירות ומחלץ טענות מ-{documents.length} מסמכים
            </p>
          </div>
        </Card>
      )}

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <div className="flex gap-8">
          {[
            { id: 'documents', label: 'מסמכים', icon: FileText, count: documents.length },
            { id: 'analysis', label: 'ניתוח', icon: Search, count: analysisRuns.length },
            { id: 'history', label: 'היסטוריה', icon: Clock },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as Tab)}
              className={`flex items-center gap-2 py-4 border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-primary-500 text-primary-600 font-semibold'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              <tab.icon className="w-5 h-5" />
              {tab.label}
              {tab.count !== undefined && (
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-xs">
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        {activeTab === 'documents' && (
          <motion.div
            key="documents"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            {documents.length === 0 ? (
              <EmptyState
                icon={<FileText className="w-16 h-16" />}
                title="אין מסמכים בתיק"
                description="העלו מסמכים כדי להתחיל בניתוח"
                action={{
                  label: 'העלה מסמכים',
                  onClick: () => setShowUploadModal(true),
                  icon: <Upload className="w-5 h-5" />,
                }}
              />
            ) : (
              <Card padding="none">
                <div className="divide-y divide-slate-100">
                  {documents.map((doc) => (
                    <motion.div
                      key={doc.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="p-4 hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center text-2xl">
                          {getFileIcon(doc.mime_type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium text-slate-900 truncate">
                              {doc.doc_name || doc.original_filename}
                            </h3>
                            {getStatusBadge(doc.status)}
                          </div>
                          <div className="flex items-center gap-3 text-sm text-slate-500 mt-1">
                            {doc.page_count && <span>{doc.page_count} עמודים</span>}
                            {doc.party && <span>צד: {doc.party}</span>}
                            <span>{new Date(doc.created_at).toLocaleDateString('he-IL')}</span>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => navigate(`/documents/${doc.id}`)}
                          leftIcon={<Eye className="w-4 h-4" />}
                        >
                          צפייה
                        </Button>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </Card>
            )}
          </motion.div>
        )}

        {activeTab === 'analysis' && (
          <motion.div
            key="analysis"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            {analysisRuns.length === 0 ? (
              <EmptyState
                icon={<Search className="w-16 h-16" />}
                title="לא בוצע ניתוח עדיין"
                description="הפעילו ניתוח כדי לזהות סתירות בין המסמכים"
                action={{
                  label: 'הפעל ניתוח',
                  onClick: handleAnalyze,
                  icon: <Play className="w-5 h-5" />,
                }}
              />
            ) : (
              <div className="space-y-4">
                {analysisRuns.map((run) => (
                  <Card
                    key={run.id}
                    variant="interactive"
                    onClick={() => navigate(`/analysis/${run.id}`)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-3">
                          <h3 className="font-bold text-slate-900">
                            ניתוח #{run.id.slice(0, 8)}
                          </h3>
                          {getStatusBadge(run.status)}
                        </div>
                        <p className="text-sm text-slate-500 mt-1">
                          {new Date(run.created_at).toLocaleString('he-IL')}
                        </p>
                      </div>
                      <div className="flex items-center gap-8 text-center">
                        <div>
                          <div className="text-2xl font-bold text-slate-900">
                            {run.claims_count || 0}
                          </div>
                          <div className="text-xs text-slate-500">טענות</div>
                        </div>
                        <div>
                          <div className="text-2xl font-bold text-warning-600">
                            {run.contradictions_count || 0}
                          </div>
                          <div className="text-xs text-slate-500">סתירות</div>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'history' && (
          <motion.div
            key="history"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            <EmptyState
              icon={<Clock className="w-16 h-16" />}
              title="היסטוריית פעילות"
              description="כאן תוצג היסטוריית הפעולות בתיק"
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Upload Modal */}
      <Modal
        isOpen={showUploadModal}
        onClose={() => {
          setShowUploadModal(false);
          setUploadFiles([]);
          setUploadError('');
        }}
        title="העלאת מסמכים"
        description="העלו מסמכים לתיק לצורך ניתוח"
        size="lg"
      >
        <div className="space-y-6">
          {uploadError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {uploadError}
            </div>
          )}

          {/* Drop zone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleFileDrop}
            className="border-2 border-dashed border-slate-300 rounded-2xl p-8 text-center hover:border-primary-400 hover:bg-primary-50/50 transition-colors cursor-pointer"
          >
            <input
              type="file"
              multiple
              accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg"
              onChange={handleFileSelect}
              className="hidden"
              id="file-upload"
            />
            <label htmlFor="file-upload" className="cursor-pointer">
              <Upload className="w-12 h-12 text-slate-400 mx-auto mb-4" />
              <p className="text-lg font-medium text-slate-700">
                גררו קבצים לכאן או לחצו לבחירה
              </p>
              <p className="text-sm text-slate-500 mt-2">
                PDF, DOCX, TXT, PNG, JPG עד 25MB לקובץ
              </p>
            </label>
          </div>

          {/* Selected files */}
          {uploadFiles.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-medium text-slate-900">
                קבצים נבחרים ({uploadFiles.length})
              </h4>
              <div className="max-h-48 overflow-y-auto space-y-2">
                {uploadFiles.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-slate-50 rounded-xl"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{getFileIcon(file.type)}</span>
                      <div>
                        <p className="font-medium text-slate-900 text-sm">{file.name}</p>
                        <p className="text-xs text-slate-500">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() =>
                        setUploadFiles(uploadFiles.filter((_, i) => i !== index))
                      }
                      className="p-2 text-slate-400 hover:text-danger-600 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upload progress */}
          {isUploading && (
            <Progress value={uploadProgress} label="מעלה קבצים..." showLabel />
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <Button
              onClick={handleUpload}
              className="flex-1"
              isLoading={isUploading}
              disabled={uploadFiles.length === 0}
            >
              העלה {uploadFiles.length} קבצים
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setShowUploadModal(false);
                setUploadFiles([]);
              }}
            >
              ביטול
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default CaseDetailPage;
