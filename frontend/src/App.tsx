import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import { ToastProvider } from './components/ui/Toast';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/layout';
import { NotebookLayout } from './components/notebook';
import {
  LoginPage,
  RegisterPage,
  ForgotPasswordPage,
  ResetPasswordPage,
  CasesPage,
  CaseDetailPage,
  DocumentDetailPage,
  AnalyzePage,
  SettingsPage,
  TeamsPage,
  UsersPage,
  ExpertNotebookPage,
} from './pages';
import {
  NotebooksListPage,
  SourcesTab,
  TimelineTab,
  FindingsTab,
  CrossExamTab,
  WitnessesTab,
  NotesTab,
} from './pages/notebooks';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

function App() {
  return (
    <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <Router>
            <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* Protected routes */}
            <Route element={<Layout />}>
              {/* Notebook routes (primary) */}
              <Route path="/notebooks" element={<NotebooksListPage />} />
              <Route path="/notebooks/new" element={<CasesPage />} />
              <Route path="/notebooks/:notebookId" element={<NotebookLayout />}>
                <Route index element={<Navigate to="findings" replace />} />
                <Route path="sources" element={<SourcesTab />} />
                <Route path="timeline" element={<TimelineTab />} />
                <Route path="findings" element={<FindingsTab />} />
                <Route path="crossexam" element={<CrossExamTab />} />
                <Route path="witnesses" element={<WitnessesTab />} />
                <Route path="notes" element={<NotesTab />} />
              </Route>

              {/* Legacy routes (redirect to notebook equivalents) */}
              <Route path="/dashboard" element={<Navigate to="/notebooks" replace />} />
              <Route path="/cases" element={<Navigate to="/notebooks" replace />} />
              <Route path="/cases/new" element={<Navigate to="/notebooks/new" replace />} />
              <Route path="/cases/:caseId" element={<CaseDetailPage />} />
              <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
              <Route path="/analyze" element={<AnalyzePage />} />
              <Route path="/expert-notebook" element={<ExpertNotebookPage />} />

              {/* Settings (consolidated) */}
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/teams" element={<TeamsPage />} />
              <Route path="/users" element={<UsersPage />} />
            </Route>

            {/* Redirects */}
            <Route path="/" element={<Navigate to="/notebooks" replace />} />
            <Route path="*" element={<Navigate to="/notebooks" replace />} />
          </Routes>
          </Router>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
