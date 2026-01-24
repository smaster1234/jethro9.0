import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  FileText,
  Download,
  Calendar,
  User,
  Hash,
  Globe,
  CheckCircle,
  Clock,
  AlertTriangle,
  RefreshCw,
  Copy,
} from 'lucide-react';
import { documentsApi, handleApiError } from '../api';
import {
  Card,
  Button,
  Badge,
  Spinner,
  EmptyState,
} from '../components/ui';
import type { Document } from '../types';

interface DocumentText {
  doc_id: string;
  doc_name: string;
  text: string;
  page_count: number;
}

export const DocumentDetailPage: React.FC = () => {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();

  const [document, setDocument] = useState<Document | null>(null);
  const [documentText, setDocumentText] = useState<DocumentText | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingText, setIsLoadingText] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (documentId) {
      fetchDocument();
    }
  }, [documentId]);

  const fetchDocument = async () => {
    if (!documentId) return;

    setIsLoading(true);
    setError('');

    try {
      const [docRes, textRes] = await Promise.all([
        documentsApi.get(documentId),
        documentsApi.getText(documentId).catch(() => null),
      ]);

      setDocument(docRes);
      setDocumentText(textRes);
    } catch (err) {
      console.error('Failed to fetch document:', err);
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefreshText = async () => {
    if (!documentId) return;

    setIsLoadingText(true);
    try {
      const textRes = await documentsApi.getText(documentId);
      setDocumentText(textRes);
    } catch (err) {
      console.error('Failed to refresh text:', err);
    } finally {
      setIsLoadingText(false);
    }
  };

  const handleCopyText = () => {
    if (documentText?.text) {
      navigator.clipboard.writeText(documentText.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success" icon={<CheckCircle className="w-3 h-3" />}>הושלם</Badge>;
      case 'processing':
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

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'לא ידוע';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !document) {
    return (
      <EmptyState
        icon={<AlertTriangle className="w-16 h-16" />}
        title="מסמך לא נמצא"
        description={error || "המסמך המבוקש אינו קיים או שאין לך הרשאה לצפות בו"}
        action={{
          label: 'חזרה',
          onClick: () => navigate(-1),
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-4 transition-colors"
        >
          <ArrowRight className="w-4 h-4" />
          חזרה
        </button>

        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center text-4xl">
              {getFileIcon(document.mime_type)}
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-slate-900">
                  {document.doc_name || document.original_filename || 'מסמך ללא שם'}
                </h1>
                {getStatusBadge(document.status)}
              </div>
              {document.original_filename && document.doc_name !== document.original_filename && (
                <p className="text-slate-500 mt-1">
                  שם מקורי: {document.original_filename}
                </p>
              )}
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={handleCopyText}
              disabled={!documentText?.text}
              leftIcon={copied ? <CheckCircle className="w-5 h-5 text-success-500" /> : <Copy className="w-5 h-5" />}
            >
              {copied ? 'הועתק!' : 'העתק טקסט'}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Document Info */}
        <div className="space-y-4">
          <Card>
            <h3 className="font-bold text-slate-900 mb-4">פרטי המסמך</h3>
            <div className="space-y-3">
              {document.page_count && (
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-primary-50 flex items-center justify-center">
                    <FileText className="w-5 h-5 text-primary-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">עמודים</p>
                    <p className="font-medium text-slate-900">{document.page_count}</p>
                  </div>
                </div>
              )}

              {document.size_bytes && (
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-accent-50 flex items-center justify-center">
                    <Download className="w-5 h-5 text-accent-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">גודל</p>
                    <p className="font-medium text-slate-900">{formatFileSize(document.size_bytes)}</p>
                  </div>
                </div>
              )}

              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-success-50 flex items-center justify-center">
                  <Calendar className="w-5 h-5 text-success-600" />
                </div>
                <div>
                  <p className="text-sm text-slate-500">תאריך העלאה</p>
                  <p className="font-medium text-slate-900">
                    {new Date(document.created_at).toLocaleDateString('he-IL')}
                  </p>
                </div>
              </div>

              {document.language && (
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-warning-50 flex items-center justify-center">
                    <Globe className="w-5 h-5 text-warning-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">שפה</p>
                    <p className="font-medium text-slate-900">
                      {document.language === 'he' ? 'עברית' : document.language === 'en' ? 'English' : document.language}
                    </p>
                  </div>
                </div>
              )}

              {document.party && (
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                    <User className="w-5 h-5 text-slate-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">צד</p>
                    <p className="font-medium text-slate-900">{document.party}</p>
                  </div>
                </div>
              )}

              {document.role && (
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-danger-50 flex items-center justify-center">
                    <Hash className="w-5 h-5 text-danger-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">תפקיד</p>
                    <p className="font-medium text-slate-900">{document.role}</p>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* Mime Type Info */}
          {document.mime_type && (
            <Card>
              <h3 className="font-bold text-slate-900 mb-3">סוג קובץ</h3>
              <p className="text-sm text-slate-600 font-mono bg-slate-50 p-2 rounded">
                {document.mime_type}
              </p>
            </Card>
          )}
        </div>

        {/* Document Text */}
        <div className="lg:col-span-2">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-slate-900">טקסט המסמך</h3>
              <div className="flex items-center gap-2">
                {documentText?.page_count && (
                  <span className="text-sm text-slate-500">
                    {documentText.page_count} עמודים
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleRefreshText}
                  isLoading={isLoadingText}
                  leftIcon={<RefreshCw className="w-4 h-4" />}
                >
                  רענן
                </Button>
              </div>
            </div>

            {document.status === 'processing' ? (
              <div className="text-center py-12">
                <RefreshCw className="w-12 h-12 text-warning-500 mx-auto mb-4 animate-spin" />
                <p className="text-lg font-medium text-slate-700">
                  המסמך בעיבוד
                </p>
                <p className="text-sm text-slate-500 mt-2">
                  טקסט המסמך יהיה זמין בקרוב
                </p>
              </div>
            ) : document.status === 'pending' ? (
              <div className="text-center py-12">
                <Clock className="w-12 h-12 text-slate-400 mx-auto mb-4" />
                <p className="text-lg font-medium text-slate-700">
                  ממתין לעיבוד
                </p>
                <p className="text-sm text-slate-500 mt-2">
                  המסמך נמצא בתור לעיבוד
                </p>
              </div>
            ) : document.status === 'failed' ? (
              <div className="text-center py-12">
                <AlertTriangle className="w-12 h-12 text-danger-500 mx-auto mb-4" />
                <p className="text-lg font-medium text-slate-700">
                  עיבוד נכשל
                </p>
                <p className="text-sm text-slate-500 mt-2">
                  לא ניתן לחלץ טקסט מהמסמך
                </p>
              </div>
            ) : documentText?.text ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              >
                <div
                  className="prose prose-slate max-w-none bg-slate-50 rounded-xl p-6 max-h-[600px] overflow-y-auto"
                  dir="auto"
                >
                  <pre className="whitespace-pre-wrap font-sans text-sm text-slate-700 leading-relaxed">
                    {documentText.text}
                  </pre>
                </div>
                <div className="mt-3 text-sm text-slate-500 text-left">
                  {documentText.text.length.toLocaleString()} תווים
                </div>
              </motion.div>
            ) : (
              <div className="text-center py-12">
                <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <p className="text-lg font-medium text-slate-700">
                  אין טקסט זמין
                </p>
                <p className="text-sm text-slate-500 mt-2">
                  לא נמצא טקסט במסמך זה
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};

export default DocumentDetailPage;
