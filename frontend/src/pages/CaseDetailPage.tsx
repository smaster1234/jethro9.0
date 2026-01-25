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
  FolderPlus,
  Folder,
  ChevronDown,
  ChevronLeft,
  ArrowDown,
  Copy,
  MessageSquare,
  X,
  ExternalLink,
  StickyNote,
  Plus,
  Save,
  Users,
  UserPlus,
  Mail,
  Download,
  ListOrdered,
} from 'lucide-react';
import { casesApi, documentsApi, handleApiError, witnessesApi, insightsApi, crossExamPlanApi } from '../api';
import { usersApi } from '../api/users';
import type { MemoryItem, CaseParticipant } from '../api/cases';
import type { CaseJob } from '../api/documents';
import {
  Card,
  Button,
  Badge,
  Spinner,
  EmptyState,
  Modal,
  Progress,
  Input,
} from '../components/ui';
import type {
  Case,
  Document as DocumentType,
  AnalysisRun,
  Folder as FolderType,
  Contradiction,
  CrossExamQuestion,
  CrossExamQuestionsOutput,
  EvidenceAnchor,
  Witness,
  WitnessVersionDiffResponse,
  ContradictionInsight,
  CrossExamPlanResponse,
  CrossExamPlanStep,
  WitnessSimulationResponse,
} from '../types';
import EvidenceViewerModal from '../components/EvidenceViewerModal';

// Helper to flatten cross-exam questions from nested structure
const flattenCrossExamQuestions = (
  questions: CrossExamQuestionsOutput[] | CrossExamQuestion[] | undefined
): CrossExamQuestion[] => {
  if (!questions || questions.length === 0) return [];
  const first = questions[0];
  if ('question' in first && typeof first.question === 'string') {
    return questions as CrossExamQuestion[];
  }
  return (questions as CrossExamQuestionsOutput[]).flatMap(
    (set) => set.questions || []
  );
};

const toEvidenceAnchor = (
  raw?: EvidenceAnchor | Record<string, unknown> | null
): EvidenceAnchor | null => {
  if (!raw || typeof raw !== 'object') return null;
  const data = raw as Record<string, unknown>;
  const docId = data.doc_id as string | undefined;
  if (!docId) return null;

  return {
    doc_id: docId,
    page_no: (data.page_no as number | undefined) ?? (data.page as number | undefined),
    block_index: data.block_index as number | undefined,
    paragraph_index: (data.paragraph_index as number | undefined) ?? (data.paragraph as number | undefined),
    char_start: data.char_start as number | undefined,
    char_end: data.char_end as number | undefined,
    snippet: data.snippet as string | undefined,
    bbox: data.bbox as EvidenceAnchor['bbox'],
  };
};

const anchorFromClaim = (
  claim?: { source_doc_id?: string; page_no?: number; block_index?: number }
): EvidenceAnchor | null => {
  if (!claim?.source_doc_id) return null;
  return {
    doc_id: claim.source_doc_id,
    page_no: claim.page_no,
    block_index: claim.block_index,
  };
};

type Tab = 'documents' | 'analysis' | 'witnesses' | 'notes' | 'team';

export const CaseDetailPage: React.FC = () => {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();

  const [caseData, setCaseData] = useState<Case | null>(null);
  const [documents, setDocuments] = useState<DocumentType[]>([]);
  const [folders, setFolders] = useState<FolderType[]>([]);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('documents');
  const [selectedFolderId, setSelectedFolderId] = useState<string | undefined>(undefined);

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState('');
  const [uploadFolderId, setUploadFolderId] = useState<string | undefined>(undefined);

  // Create folder state
  const [showCreateFolderModal, setShowCreateFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderParentId, setNewFolderParentId] = useState<string | undefined>(undefined);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [createFolderError, setCreateFolderError] = useState('');

  // Delete folder state
  const [showDeleteFolderModal, setShowDeleteFolderModal] = useState(false);
  const [folderToDelete, setFolderToDelete] = useState<string | null>(null);
  const [isDeletingFolder, setIsDeletingFolder] = useState(false);
  const [deleteFolderError, setDeleteFolderError] = useState('');
  const [deleteFolderRecursive, setDeleteFolderRecursive] = useState(false);

  // Analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [_currentRun, setCurrentRun] = useState<AnalysisRun | null>(null);

  // Analysis results view state
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [analysisResultsTab, setAnalysisResultsTab] = useState<'contradictions' | 'questions' | 'plan'>('contradictions');
  const [insightsByContradiction, setInsightsByContradiction] = useState<Record<string, ContradictionInsight>>({});
  const [isLoadingInsights, setIsLoadingInsights] = useState(false);
  const [crossExamPlan, setCrossExamPlan] = useState<CrossExamPlanResponse | null>(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState(false);
  const [planError, setPlanError] = useState('');
  const [simulationPersona, setSimulationPersona] = useState<'cooperative' | 'evasive' | 'hostile'>('cooperative');
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationResult, setSimulationResult] = useState<WitnessSimulationResponse | null>(null);
  const [isSimulationModalOpen, setIsSimulationModalOpen] = useState(false);

  // Witnesses state
  const [witnesses, setWitnesses] = useState<Witness[]>([]);
  const [isLoadingWitnesses, setIsLoadingWitnesses] = useState(false);
  const [newWitnessName, setNewWitnessName] = useState('');
  const [newWitnessSide, setNewWitnessSide] = useState('unknown');
  const [isCreatingWitness, setIsCreatingWitness] = useState(false);
  const [witnessError, setWitnessError] = useState('');

  // Evidence viewer state
  const [isEvidenceViewerOpen, setIsEvidenceViewerOpen] = useState(false);
  const [evidenceLeftAnchor, setEvidenceLeftAnchor] = useState<EvidenceAnchor | null>(null);
  const [evidenceRightAnchor, setEvidenceRightAnchor] = useState<EvidenceAnchor | null>(null);

  // Analysis options modal state
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [analysisMode, setAnalysisMode] = useState<'hybrid' | 'rule_based' | 'llm'>('hybrid');
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [forceReanalyze, setForceReanalyze] = useState(false);

  // Polling for jobs
  const [activeJobs, setActiveJobs] = useState<string[]>([]);

  // Notes state
  const [notes, setNotes] = useState<MemoryItem[]>([]);
  const [isLoadingNotes, setIsLoadingNotes] = useState(false);
  const [isSavingNotes, setIsSavingNotes] = useState(false);
  const [newNoteText, setNewNoteText] = useState('');
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingNoteText, setEditingNoteText] = useState('');

  // Document filters
  const [docSearchQuery, setDocSearchQuery] = useState('');
  const [docStatusFilter, setDocStatusFilter] = useState<string>('');
  const [docPartyFilter, setDocPartyFilter] = useState<string>('');
  const [docRoleFilter, setDocRoleFilter] = useState<string>('');

  // Contradiction filters
  const [contradictionSeverityFilter, setContradictionSeverityFilter] = useState<string>('');
  const [contradictionStatusFilter, setContradictionStatusFilter] = useState<string>('');
  const [contradictionSearchQuery, setContradictionSearchQuery] = useState('');

  // Jobs state
  const [caseJobs, setCaseJobs] = useState<CaseJob[]>([]);
  const [showJobsPanel, setShowJobsPanel] = useState(false);

  // Participants state
  const [participants, setParticipants] = useState<CaseParticipant[]>([]);
  const [isLoadingParticipants, setIsLoadingParticipants] = useState(false);
  const [showAddParticipantModal, setShowAddParticipantModal] = useState(false);
  const [newParticipantEmail, setNewParticipantEmail] = useState('');
  const [newParticipantRole, setNewParticipantRole] = useState('');
  const [isAddingParticipant, setIsAddingParticipant] = useState(false);
  const [addParticipantError, setAddParticipantError] = useState('');

  // Document preview state
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<DocumentType | null>(null);
  const [previewText, setPreviewText] = useState<string>('');
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  useEffect(() => {
    if (caseId) {
      fetchCaseData();
      fetchJobs();
    }
  }, [caseId]);

  // Fetch jobs periodically when there are active jobs
  useEffect(() => {
    const hasActiveJobs = caseJobs.some(j => j.status === 'queued' || j.status === 'started');
    if (!hasActiveJobs || !caseId) return;

    const interval = setInterval(() => {
      fetchJobs();
      fetchDocuments();
    }, 3000);

    return () => clearInterval(interval);
  }, [caseJobs, caseId]);

  // Fetch notes when notes tab is selected
  useEffect(() => {
    if (activeTab === 'notes' && caseId && notes.length === 0) {
      fetchNotes();
    }
  }, [activeTab, caseId]);

  // Fetch witnesses when witnesses tab is selected
  useEffect(() => {
    if (activeTab === 'witnesses' && caseId) {
      fetchWitnesses();
    }
  }, [activeTab, caseId]);

  // Fetch participants when team tab is selected
  useEffect(() => {
    if (activeTab === 'team' && caseId && participants.length === 0) {
      fetchParticipants();
    }
  }, [activeTab, caseId]);

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

  const fetchJobs = async () => {
    if (!caseId) return;
    try {
      const jobsRes = await documentsApi.listCaseJobs(caseId);
      setCaseJobs(jobsRes);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    }
  };

  const fetchFolders = async () => {
    if (!caseId) return;
    try {
      const foldersRes = await documentsApi.folders.getTree(caseId);
      setFolders(foldersRes);
    } catch (error) {
      console.error('Failed to fetch folders:', error);
    }
  };

  const fetchNotes = async () => {
    if (!caseId) return;
    setIsLoadingNotes(true);
    try {
      const memoryItems = await casesApi.getMemory(caseId);
      setNotes(memoryItems);
    } catch (error) {
      console.error('Failed to fetch notes:', error);
    } finally {
      setIsLoadingNotes(false);
    }
  };

  const fetchParticipants = async () => {
    if (!caseId) return;
    setIsLoadingParticipants(true);
    try {
      const participantsRes = await casesApi.getParticipants(caseId);
      setParticipants(participantsRes);
    } catch (error) {
      console.error('Failed to fetch participants:', error);
    } finally {
      setIsLoadingParticipants(false);
    }
  };

  const fetchWitnesses = async () => {
    if (!caseId) return;
    setIsLoadingWitnesses(true);
    try {
      const witnessRes = await witnessesApi.list(caseId);
      setWitnesses(witnessRes || []);
    } catch (error) {
      console.error('Failed to fetch witnesses:', error);
      setWitnessError(handleApiError(error));
    } finally {
      setIsLoadingWitnesses(false);
    }
  };

  const handleCreateWitness = async () => {
    if (!caseId || !newWitnessName.trim()) return;
    setIsCreatingWitness(true);
    setWitnessError('');
    try {
      await witnessesApi.create(caseId, {
        name: newWitnessName.trim(),
        side: newWitnessSide,
      });
      setNewWitnessName('');
      setNewWitnessSide('unknown');
      await fetchWitnesses();
    } catch (error) {
      setWitnessError(handleApiError(error));
    } finally {
      setIsCreatingWitness(false);
    }
  };

  const handleAddParticipant = async () => {
    if (!caseId || !newParticipantEmail.trim()) return;

    setIsAddingParticipant(true);
    setAddParticipantError('');

    try {
      // First lookup user by email
      const user = await usersApi.lookupByEmail(newParticipantEmail.trim());

      // Then add as participant
      await casesApi.addParticipant(caseId, user.id, newParticipantRole || undefined);

      // Refresh participants list
      await fetchParticipants();

      // Close modal and reset
      setShowAddParticipantModal(false);
      setNewParticipantEmail('');
      setNewParticipantRole('');
    } catch (error) {
      console.error('Failed to add participant:', error);
      const errorMessage = handleApiError(error);
      if (errorMessage.includes('not found') || errorMessage.includes('404')) {
        setAddParticipantError('משתמש עם כתובת דוא״ל זו לא נמצא במערכת');
      } else {
        setAddParticipantError(errorMessage);
      }
    } finally {
      setIsAddingParticipant(false);
    }
  };

  const handleAddNote = async () => {
    if (!caseId || !newNoteText.trim()) return;

    const newNote: MemoryItem = {
      id: crypto.randomUUID(),
      text: newNoteText.trim(),
      created_at: new Date().toISOString(),
      type: 'note',
    };

    const updatedNotes = [newNote, ...notes];
    setNotes(updatedNotes);
    setNewNoteText('');

    setIsSavingNotes(true);
    try {
      await casesApi.saveMemory(caseId, updatedNotes);
    } catch (error) {
      console.error('Failed to save note:', error);
      // Revert on error
      setNotes(notes);
      setNewNoteText(newNote.text);
    } finally {
      setIsSavingNotes(false);
    }
  };

  const handleUpdateNote = async (noteId: string) => {
    if (!caseId || !editingNoteText.trim()) return;

    const updatedNotes = notes.map((n) =>
      n.id === noteId ? { ...n, text: editingNoteText.trim() } : n
    );
    setNotes(updatedNotes);
    setEditingNoteId(null);
    setEditingNoteText('');

    setIsSavingNotes(true);
    try {
      await casesApi.saveMemory(caseId, updatedNotes);
    } catch (error) {
      console.error('Failed to update note:', error);
      await fetchNotes(); // Refresh on error
    } finally {
      setIsSavingNotes(false);
    }
  };

  const handleDeleteNote = async (noteId: string) => {
    if (!caseId) return;

    const updatedNotes = notes.filter((n) => n.id !== noteId);
    setNotes(updatedNotes);

    setIsSavingNotes(true);
    try {
      await casesApi.saveMemory(caseId, updatedNotes);
    } catch (error) {
      console.error('Failed to delete note:', error);
      await fetchNotes(); // Refresh on error
    } finally {
      setIsSavingNotes(false);
    }
  };

  const handleSelectRun = async (run: AnalysisRun) => {
    if (selectedRun?.id === run.id) {
      // Toggle off if same run clicked
      setSelectedRun(null);
      setInsightsByContradiction({});
      return;
    }

    setIsLoadingRun(true);
    try {
      const fullRun = await casesApi.getRun(run.id);
      setSelectedRun(fullRun);
      setCrossExamPlan(null);
      setPlanError('');
    } catch (error) {
      console.error('Failed to fetch run details:', error);
      // Still show basic run info
      setSelectedRun(run);
    } finally {
      setIsLoadingRun(false);
    }
  };

  useEffect(() => {
    if (!selectedRun?.id) {
      setInsightsByContradiction({});
      return;
    }
    const fetchInsights = async () => {
      setIsLoadingInsights(true);
      try {
        const insights = await insightsApi.listByRun(selectedRun.id);
        const map: Record<string, ContradictionInsight> = {};
        insights.forEach((insight) => {
          map[insight.contradiction_id] = insight;
        });
        setInsightsByContradiction(map);
      } catch (error) {
        console.error('Failed to fetch insights:', error);
      } finally {
        setIsLoadingInsights(false);
      }
    };
    fetchInsights();
  }, [selectedRun?.id]);

  useEffect(() => {
    if (!selectedRun?.id || analysisResultsTab !== 'plan') {
      return;
    }
    const loadPlan = async () => {
      setIsLoadingPlan(true);
      setPlanError('');
      try {
        const plan = await crossExamPlanApi.getLatest(selectedRun.id);
        setCrossExamPlan(plan);
      } catch (error) {
        setCrossExamPlan(null);
        setPlanError(handleApiError(error));
      } finally {
        setIsLoadingPlan(false);
      }
    };
    loadPlan();
  }, [selectedRun?.id, analysisResultsTab]);

  const handleCreateFolder = async () => {
    if (!caseId || !newFolderName.trim()) return;

    setIsCreatingFolder(true);
    setCreateFolderError('');

    try {
      await documentsApi.folders.create(caseId, newFolderName.trim(), newFolderParentId);
      setShowCreateFolderModal(false);
      setNewFolderName('');
      setNewFolderParentId(undefined);
      await fetchFolders();
    } catch (error) {
      setCreateFolderError(handleApiError(error));
    } finally {
      setIsCreatingFolder(false);
    }
  };

  const handleDeleteFolderClick = (folderId: string) => {
    setFolderToDelete(folderId);
    setDeleteFolderError('');
    setDeleteFolderRecursive(false);
    setShowDeleteFolderModal(true);
  };

  const handleDeleteFolder = async () => {
    if (!folderToDelete) return;

    setIsDeletingFolder(true);
    setDeleteFolderError('');

    try {
      await documentsApi.folders.delete(folderToDelete, deleteFolderRecursive);
      setShowDeleteFolderModal(false);
      setFolderToDelete(null);
      // If we deleted the selected folder, clear selection
      if (selectedFolderId === folderToDelete) {
        setSelectedFolderId(undefined);
      }
      await fetchFolders();
      await fetchDocuments();
    } catch (error) {
      setDeleteFolderError(handleApiError(error));
    } finally {
      setIsDeletingFolder(false);
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

      const result = await documentsApi.upload(caseId, uploadFiles, metadata, uploadFolderId);

      // Track active jobs
      if (result.job_ids && result.job_ids.length > 0) {
        setActiveJobs(result.job_ids);
      }

      setUploadFiles([]);
      setUploadFolderId(undefined);
      setShowUploadModal(false);
      await fetchDocuments();
    } catch (error) {
      setUploadError(handleApiError(error));
    } finally {
      setIsUploading(false);
    }
  };

  const handlePreviewDoc = async (doc: DocumentType) => {
    setPreviewDoc(doc);
    setPreviewText('');
    setShowPreviewModal(true);
    setIsLoadingPreview(true);

    try {
      const textData = await documentsApi.getText(doc.id);
      setPreviewText(textData.text || '');
    } catch (error) {
      console.error('Failed to load document text:', error);
      setPreviewText('שגיאה בטעינת טקסט המסמך');
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleExportContradictions = (contradictions: Contradiction[], format: 'csv' | 'text' = 'csv') => {
    if (!contradictions || contradictions.length === 0) return;

    const caseName = caseData?.name || 'case';
    const date = new Date().toISOString().split('T')[0];

    if (format === 'csv') {
      // CSV export
      const headers = ['מספר', 'חומרה', 'סטטוס', 'קטגוריה', 'הסבר', 'ציטוט 1', 'ציטוט 2'];
      const rows = contradictions.map((c, i) => [
        i + 1,
        c.severity || '',
        c.status || '',
        c.category || '',
        `"${(c.explanation || '').replace(/"/g, '""')}"`,
        `"${(c.quote1 || '').replace(/"/g, '""')}"`,
        `"${(c.quote2 || '').replace(/"/g, '""')}"`,
      ]);

      const csvContent = '\uFEFF' + headers.join(',') + '\n' + rows.map(r => r.join(',')).join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `contradictions_${caseName}_${date}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } else {
      // Text report export
      let report = `דוח סתירות - ${caseName}\n`;
      report += `תאריך: ${new Date().toLocaleDateString('he-IL')}\n`;
      report += `סה"כ סתירות: ${contradictions.length}\n`;
      report += '='.repeat(50) + '\n\n';

      contradictions.forEach((c, i) => {
        report += `סתירה #${i + 1}\n`;
        report += `-`.repeat(30) + '\n';
        report += `חומרה: ${c.severity || 'לא מוגדר'}\n`;
        report += `סטטוס: ${c.status || 'לא מוגדר'}\n`;
        report += `קטגוריה: ${c.category || 'לא מוגדר'}\n\n`;
        report += `הסבר:\n${c.explanation || 'אין הסבר'}\n\n`;
        if (c.quote1) report += `ציטוט 1:\n"${c.quote1}"\n\n`;
        if (c.quote2) report += `ציטוט 2:\n"${c.quote2}"\n\n`;
        report += '\n';
      });

      const blob = new Blob([report], { type: 'text/plain;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `contradictions_report_${caseName}_${date}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }
  };

  const handleShowEvidence = useCallback((contradiction: Contradiction) => {
    const left = toEvidenceAnchor(contradiction.claim1_locator) || anchorFromClaim(contradiction.claim_a);
    const right = toEvidenceAnchor(contradiction.claim2_locator) || anchorFromClaim(contradiction.claim_b);

    setEvidenceLeftAnchor(left);
    setEvidenceRightAnchor(right);
    setIsEvidenceViewerOpen(true);
  }, []);

  const handleShowEvidenceAnchors = useCallback((left?: EvidenceAnchor | null, right?: EvidenceAnchor | null) => {
    setEvidenceLeftAnchor(left || null);
    setEvidenceRightAnchor(right || null);
    setIsEvidenceViewerOpen(true);
  }, []);

  const handleGeneratePlan = async () => {
    if (!selectedRun?.id) return;
    setIsLoadingPlan(true);
    setPlanError('');
    try {
      const plan = await crossExamPlanApi.generate(selectedRun.id, {});
      setCrossExamPlan(plan);
    } catch (error) {
      setPlanError(handleApiError(error));
    } finally {
      setIsLoadingPlan(false);
    }
  };

  const handleSimulateWitness = async () => {
    if (!selectedRun?.id) return;
    setIsSimulating(true);
    try {
      const result = await crossExamPlanApi.simulateWitness(selectedRun.id, {
        persona: simulationPersona,
        plan_id: crossExamPlan?.plan_id,
      });
      setSimulationResult(result);
      setIsSimulationModalOpen(true);
    } catch (error) {
      setPlanError(handleApiError(error));
    } finally {
      setIsSimulating(false);
    }
  };

  const handleExportPlan = async (format: 'docx' | 'pdf') => {
    if (!selectedRun?.id) return;
    try {
      const blob = await crossExamPlanApi.exportPlan(selectedRun.id, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `cross_exam_plan_${selectedRun.id}.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      setPlanError(handleApiError(error));
    }
  };

  const handleAnalyze = async () => {
    if (!caseId) return;

    setIsAnalyzing(true);
    setAnalysisProgress(0);
    setShowAnalysisModal(false);

    try {
      const result = await casesApi.analyze(caseId, {
        force: forceReanalyze,
        mode: analysisMode,
        document_ids: selectedDocIds.length > 0 ? selectedDocIds : undefined,
      });

      // Reset options
      setForceReanalyze(false);
      setSelectedDocIds([]);

      // If result is cached, show immediately
      if (result.cached && result.run_id) {
        setAnalysisProgress(100);
        const runs = await casesApi.listRuns(caseId);
        setAnalysisRuns(runs);
        setActiveTab('analysis');
        const run = await casesApi.getRun(result.run_id);
        setCurrentRun(run);
        setSelectedRun(run);
        setIsAnalyzing(false);
        return;
      }

      // For non-cached results, poll for job completion
      // Start with optimistic progress
      let progress = 10;
      const progressInterval = setInterval(() => {
        progress = Math.min(progress + 5, 85);
        setAnalysisProgress(progress);
      }, 1000);

      // Poll jobs to check status
      const pollInterval = setInterval(async () => {
        try {
          const jobs = await documentsApi.listCaseJobs(caseId);
          const activeJob = jobs.find(j => j.status === 'started' || j.status === 'queued');

          if (activeJob?.progress) {
            setAnalysisProgress(Math.max(progress, activeJob.progress));
          }

          // Check if all jobs are done
          const pendingJobs = jobs.filter(j => j.status === 'queued' || j.status === 'started');
          if (pendingJobs.length === 0) {
            clearInterval(pollInterval);
            clearInterval(progressInterval);
            setAnalysisProgress(100);

            // Refresh runs and show results
            const runs = await casesApi.listRuns(caseId);
            setAnalysisRuns(runs);
            setActiveTab('analysis');

            if (result.run_id) {
              const run = await casesApi.getRun(result.run_id);
              setCurrentRun(run);
              setSelectedRun(run);
            } else if (runs.length > 0) {
              const latestRun = await casesApi.getRun(runs[0].id);
              setSelectedRun(latestRun);
            }

            setIsAnalyzing(false);
          }
        } catch (err) {
          console.error('Poll error:', err);
        }
      }, 2000);

      // Timeout after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        clearInterval(progressInterval);
        setAnalysisProgress(100);
        setIsAnalyzing(false);
      }, 300000);

    } catch (error) {
      console.error('Analysis failed:', error);
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

  // Filter documents based on search and filters
  const filteredDocuments = documents.filter((doc) => {
    // Folder filter
    if (selectedFolderId && doc.metadata?.folder_id !== selectedFolderId) {
      return false;
    }

    // Search query
    if (docSearchQuery) {
      const query = docSearchQuery.toLowerCase();
      const name = (doc.doc_name || doc.original_filename || '').toLowerCase();
      if (!name.includes(query)) {
        return false;
      }
    }

    // Status filter
    if (docStatusFilter && doc.status !== docStatusFilter) {
      return false;
    }

    // Party filter
    if (docPartyFilter && doc.party !== docPartyFilter) {
      return false;
    }

    // Role filter
    if (docRoleFilter && doc.role !== docRoleFilter) {
      return false;
    }

    return true;
  });

  // Get unique parties and roles for filter dropdowns
  const uniqueParties = [...new Set(documents.map((d) => d.party).filter(Boolean))];
  const uniqueRoles = [...new Set(documents.map((d) => d.role).filter(Boolean))];

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
            onClick={() => setShowAnalysisModal(true)}
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
            { id: 'witnesses', label: 'עדים', icon: Users, count: witnesses.length || undefined },
            { id: 'notes', label: 'הערות', icon: StickyNote, count: notes.length || undefined },
            { id: 'team', label: 'צוות', icon: Users, count: participants.length || undefined },
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
            className="space-y-4"
          >
            {/* Jobs Status */}
            {caseJobs.length > 0 && (
              <Card>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {caseJobs.some(j => j.status === 'queued' || j.status === 'started') ? (
                      <>
                        <RefreshCw className="w-5 h-5 text-primary-500 animate-spin" />
                        <span className="font-medium text-slate-900">
                          {caseJobs.filter(j => j.status === 'queued' || j.status === 'started').length} עבודות פעילות
                        </span>
                      </>
                    ) : (
                      <>
                        <CheckCircle className="w-5 h-5 text-success-500" />
                        <span className="font-medium text-slate-900">כל העבודות הושלמו</span>
                      </>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowJobsPanel(!showJobsPanel)}
                    leftIcon={showJobsPanel ? <ChevronDown className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
                  >
                    {showJobsPanel ? 'הסתר' : 'הצג פרטים'}
                  </Button>
                </div>

                {/* Expanded Jobs List */}
                {showJobsPanel && (
                  <div className="mt-4 pt-4 border-t border-slate-100 space-y-2">
                    {caseJobs.slice(0, 10).map((job) => (
                      <div key={job.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                        <div className="flex items-center gap-3">
                          {job.status === 'queued' && <Clock className="w-4 h-4 text-slate-400" />}
                          {job.status === 'started' && <RefreshCw className="w-4 h-4 text-primary-500 animate-spin" />}
                          {job.status === 'finished' && <CheckCircle className="w-4 h-4 text-success-500" />}
                          {job.status === 'failed' && <AlertTriangle className="w-4 h-4 text-danger-500" />}
                          <div>
                            <p className="text-sm font-medium text-slate-700">
                              {job.job_type === 'parse' ? 'עיבוד מסמך' :
                               job.job_type === 'analyze' ? 'ניתוח' : job.job_type}
                            </p>
                            <p className="text-xs text-slate-500">
                              {new Date(job.created_at).toLocaleString('he-IL')}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {job.progress !== undefined && job.progress < 100 && (
                            <div className="w-20">
                              <Progress value={job.progress} size="sm" />
                            </div>
                          )}
                          <Badge
                            variant={
                              job.status === 'finished' ? 'success' :
                              job.status === 'failed' ? 'danger' :
                              job.status === 'started' ? 'warning' : 'neutral'
                            }
                          >
                            {job.status === 'queued' ? 'ממתין' :
                             job.status === 'started' ? 'בעיבוד' :
                             job.status === 'finished' ? 'הושלם' : 'נכשל'}
                          </Badge>
                        </div>
                      </div>
                    ))}
                    {caseJobs.length > 10 && (
                      <p className="text-sm text-slate-500 text-center">
                        ועוד {caseJobs.length - 10} עבודות...
                      </p>
                    )}
                  </div>
                )}
              </Card>
            )}

            <div className="flex gap-6">
              {/* Folder Sidebar */}
              <div className="w-64 flex-shrink-0">
                <Card>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-slate-900">תיקיות</h3>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowCreateFolderModal(true)}
                      leftIcon={<FolderPlus className="w-4 h-4" />}
                    >
                      חדש
                    </Button>
                  </div>

                  {/* All Documents */}
                  <button
                    onClick={() => setSelectedFolderId(undefined)}
                    className={`w-full flex items-center gap-2 p-2 rounded-lg transition-colors ${
                      selectedFolderId === undefined
                        ? 'bg-primary-50 text-primary-700'
                        : 'hover:bg-slate-50 text-slate-700'
                    }`}
                  >
                    <FileText className="w-4 h-4" />
                    <span className="text-sm font-medium">כל המסמכים</span>
                    <span className="mr-auto text-xs text-slate-400">({documents.length})</span>
                  </button>

                  {/* Folder Tree */}
                  {folders.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {folders.map((folder) => (
                        <FolderTreeItem
                          key={folder.id}
                          folder={folder}
                          selectedFolderId={selectedFolderId}
                          onSelect={setSelectedFolderId}
                          onDelete={handleDeleteFolderClick}
                          level={0}
                        />
                      ))}
                    </div>
                  )}

                  {folders.length === 0 && (
                    <div className="text-center py-4 text-sm text-slate-500">
                      אין תיקיות עדיין
                    </div>
                  )}
                </Card>
              </div>

              {/* Documents List */}
              <div className="flex-1 space-y-4">
                {/* Document Search and Filters */}
                {documents.length > 0 && (
                  <Card>
                    <div className="flex flex-col md:flex-row gap-3">
                      {/* Search */}
                      <div className="flex-1">
                        <Input
                          placeholder="חיפוש לפי שם מסמך..."
                          value={docSearchQuery}
                          onChange={(e) => setDocSearchQuery(e.target.value)}
                          leftIcon={<Search className="w-5 h-5" />}
                        />
                      </div>

                      {/* Filters */}
                      <div className="flex gap-2 flex-wrap">
                        {/* Status Filter */}
                        <div className="relative">
                          <select
                            value={docStatusFilter}
                            onChange={(e) => setDocStatusFilter(e.target.value)}
                            className="appearance-none pl-8 pr-4 py-2.5 rounded-xl border-2 border-slate-200 bg-white text-slate-900 text-sm font-medium focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none cursor-pointer"
                          >
                            <option value="">כל הסטטוסים</option>
                            <option value="completed">הושלם</option>
                            <option value="processing">בעיבוד</option>
                            <option value="pending">ממתין</option>
                            <option value="failed">נכשל</option>
                          </select>
                          <ChevronDown className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                        </div>

                        {/* Party Filter */}
                        {uniqueParties.length > 0 && (
                          <div className="relative">
                            <select
                              value={docPartyFilter}
                              onChange={(e) => setDocPartyFilter(e.target.value)}
                              className="appearance-none pl-8 pr-4 py-2.5 rounded-xl border-2 border-slate-200 bg-white text-slate-900 text-sm font-medium focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none cursor-pointer"
                            >
                              <option value="">כל הצדדים</option>
                              {uniqueParties.map((party) => (
                                <option key={party} value={party}>{party}</option>
                              ))}
                            </select>
                            <ChevronDown className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                          </div>
                        )}

                        {/* Role Filter */}
                        {uniqueRoles.length > 0 && (
                          <div className="relative">
                            <select
                              value={docRoleFilter}
                              onChange={(e) => setDocRoleFilter(e.target.value)}
                              className="appearance-none pl-8 pr-4 py-2.5 rounded-xl border-2 border-slate-200 bg-white text-slate-900 text-sm font-medium focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none cursor-pointer"
                            >
                              <option value="">כל התפקידים</option>
                              {uniqueRoles.map((role) => (
                                <option key={role} value={role}>{role}</option>
                              ))}
                            </select>
                            <ChevronDown className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                          </div>
                        )}

                        {/* Clear Filters */}
                        {(docSearchQuery || docStatusFilter || docPartyFilter || docRoleFilter) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setDocSearchQuery('');
                              setDocStatusFilter('');
                              setDocPartyFilter('');
                              setDocRoleFilter('');
                            }}
                            leftIcon={<X className="w-4 h-4" />}
                          >
                            נקה
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Results count */}
                    {(docSearchQuery || docStatusFilter || docPartyFilter || docRoleFilter) && (
                      <div className="mt-3 pt-3 border-t border-slate-100 text-sm text-slate-500">
                        נמצאו {filteredDocuments.length} מתוך {documents.length} מסמכים
                      </div>
                    )}
                  </Card>
                )}

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
                ) : filteredDocuments.length === 0 ? (
                  <Card>
                    <div className="text-center py-8">
                      <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                      <p className="text-lg font-medium text-slate-700">לא נמצאו מסמכים</p>
                      <p className="text-sm text-slate-500 mt-2">נסו לשנות את הסינון או החיפוש</p>
                    </div>
                  </Card>
                ) : (
                  <Card padding="none">
                    <div className="divide-y divide-slate-100">
                      {filteredDocuments.map((doc) => (
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
                            <div className="flex gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handlePreviewDoc(doc)}
                                leftIcon={<Eye className="w-4 h-4" />}
                              >
                                תצוגה מקדימה
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => navigate(`/documents/${doc.id}`)}
                                leftIcon={<FileText className="w-4 h-4" />}
                              >
                                פרטים
                              </Button>
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            </div>
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
                {/* Analysis Runs List */}
                {!selectedRun && (
                  <>
                    {analysisRuns.map((run) => (
                      <Card
                        key={run.id}
                        variant="interactive"
                        onClick={() => handleSelectRun(run)}
                        className="cursor-pointer"
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
                            <Eye className="w-5 h-5 text-slate-400" />
                          </div>
                        </div>
                      </Card>
                    ))}
                  </>
                )}

                {/* Loading state */}
                {isLoadingRun && (
                  <Card className="flex items-center justify-center py-12">
                    <Spinner size="lg" />
                    <span className="mr-3 text-slate-600">טוען תוצאות ניתוח...</span>
                  </Card>
                )}

                {/* Selected Run Results */}
                {selectedRun && !isLoadingRun && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-4"
                  >
                    {/* Header with back button */}
                    <Card>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <button
                            onClick={() => setSelectedRun(null)}
                            className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                          >
                            <X className="w-5 h-5 text-slate-500" />
                          </button>
                          <div>
                            <h3 className="font-bold text-slate-900">
                              ניתוח #{selectedRun.id.slice(0, 8)}
                            </h3>
                            <p className="text-sm text-slate-500">
                              {new Date(selectedRun.created_at).toLocaleString('he-IL')}
                            </p>
                          </div>
                          {getStatusBadge(selectedRun.status)}
                        </div>
                        <div className="flex items-center gap-6 text-center">
                          <div>
                            <div className="text-2xl font-bold text-slate-900">
                              {selectedRun.claims_count || 0}
                            </div>
                            <div className="text-xs text-slate-500">טענות</div>
                          </div>
                          <div>
                            <div className="text-2xl font-bold text-warning-600">
                              {selectedRun.contradictions?.length || selectedRun.contradictions_count || 0}
                            </div>
                            <div className="text-xs text-slate-500">סתירות</div>
                          </div>
                        </div>
                      </div>
                    </Card>

                    {/* Results Tabs */}
                    <div className="flex items-center justify-between">
                      <div className="flex gap-2">
                        <Button
                          variant={analysisResultsTab === 'contradictions' ? 'primary' : 'secondary'}
                          size="sm"
                          onClick={() => setAnalysisResultsTab('contradictions')}
                          leftIcon={<AlertTriangle className="w-4 h-4" />}
                        >
                          סתירות ({selectedRun.contradictions?.length || 0})
                        </Button>
                        <Button
                          variant={analysisResultsTab === 'questions' ? 'primary' : 'secondary'}
                          size="sm"
                          onClick={() => setAnalysisResultsTab('questions')}
                          leftIcon={<MessageSquare className="w-4 h-4" />}
                        >
                          שאלות לחקירה
                        </Button>
                        <Button
                          variant={analysisResultsTab === 'plan' ? 'primary' : 'secondary'}
                          size="sm"
                          onClick={() => setAnalysisResultsTab('plan')}
                          leftIcon={<ListOrdered className="w-4 h-4" />}
                        >
                          תכנית חקירה
                        </Button>
                      </div>
                      {selectedRun.contradictions && selectedRun.contradictions.length > 0 && (
                        <div className="flex gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleExportContradictions(selectedRun.contradictions || [], 'csv')}
                            leftIcon={<Download className="w-4 h-4" />}
                          >
                            ייצוא CSV
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleExportContradictions(selectedRun.contradictions || [], 'text')}
                            leftIcon={<FileText className="w-4 h-4" />}
                          >
                            ייצוא דוח
                          </Button>
                        </div>
                      )}
                    </div>

                    {/* Results Content */}
                    <AnimatePresence mode="wait">
                      {analysisResultsTab === 'contradictions' && (
                        <motion.div
                          key="contradictions"
                          initial={{ opacity: 0, x: 20 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: -20 }}
                          className="space-y-4"
                        >
                          {/* Contradiction Filters */}
                          {selectedRun.contradictions && selectedRun.contradictions.length > 0 && (
                            <Card padding="sm">
                              <div className="flex flex-wrap gap-3 items-center">
                                <div className="flex-1 min-w-[200px]">
                                  <input
                                    type="text"
                                    value={contradictionSearchQuery}
                                    onChange={(e) => setContradictionSearchQuery(e.target.value)}
                                    placeholder="חיפוש בסתירות..."
                                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 outline-none"
                                  />
                                </div>
                                <select
                                  value={contradictionSeverityFilter}
                                  onChange={(e) => setContradictionSeverityFilter(e.target.value)}
                                  className="px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 outline-none"
                                >
                                  <option value="">כל החומרות</option>
                                  <option value="critical">קריטי</option>
                                  <option value="high">גבוה</option>
                                  <option value="medium">בינוני</option>
                                  <option value="low">נמוך</option>
                                </select>
                                <select
                                  value={contradictionStatusFilter}
                                  onChange={(e) => setContradictionStatusFilter(e.target.value)}
                                  className="px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 outline-none"
                                >
                                  <option value="">כל הסטטוסים</option>
                                  <option value="new">חדש</option>
                                  <option value="reviewed">נבדק</option>
                                  <option value="confirmed">מאושר</option>
                                  <option value="dismissed">נדחה</option>
                                </select>
                                {(contradictionSearchQuery || contradictionSeverityFilter || contradictionStatusFilter) && (
                                  <button
                                    onClick={() => {
                                      setContradictionSearchQuery('');
                                      setContradictionSeverityFilter('');
                                      setContradictionStatusFilter('');
                                    }}
                                    className="px-3 py-2 text-sm text-slate-500 hover:text-slate-700"
                                  >
                                    נקה סינון
                                  </button>
                                )}
                              </div>
                            </Card>
                          )}

                          {(() => {
                            // Apply filters to contradictions
                            const filtered = (selectedRun.contradictions || []).filter((c) => {
                              // Severity filter
                              if (contradictionSeverityFilter && c.severity !== contradictionSeverityFilter) {
                                return false;
                              }
                              // Status filter
                              if (contradictionStatusFilter && c.status !== contradictionStatusFilter) {
                                return false;
                              }
                              // Search query
                              if (contradictionSearchQuery) {
                                const query = contradictionSearchQuery.toLowerCase();
                                const matchText = [
                                  c.explanation,
                                  c.quote1,
                                  c.quote2,
                                  c.claim1_text,
                                  c.claim2_text,
                                  c.category,
                                  c.type,
                                ].filter(Boolean).join(' ').toLowerCase();
                                if (!matchText.includes(query)) {
                                  return false;
                                }
                              }
                              return true;
                            });

                            if (!selectedRun.contradictions || selectedRun.contradictions.length === 0) {
                              return (
                                <Card>
                                  <div className="text-center py-8">
                                    <CheckCircle className="w-12 h-12 text-success-500 mx-auto mb-4" />
                                    <p className="text-lg font-medium text-slate-700">
                                      לא נמצאו סתירות
                                    </p>
                                    <p className="text-sm text-slate-500 mt-2">
                                      המסמכים נראים עקביים ללא סתירות ברורות
                                    </p>
                                  </div>
                                </Card>
                              );
                            }

                            if (filtered.length === 0) {
                              return (
                                <Card>
                                  <div className="text-center py-8">
                                    <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                    <p className="text-lg font-medium text-slate-700">
                                      אין תוצאות לסינון
                                    </p>
                                    <p className="text-sm text-slate-500 mt-2">
                                      נסה לשנות את הגדרות הסינון
                                    </p>
                                  </div>
                                </Card>
                              );
                            }

                            return (
                              <>
                                <p className="text-sm text-slate-500">
                                  מציג {filtered.length} מתוך {selectedRun.contradictions.length} סתירות
                                </p>
                                {isLoadingInsights && (
                                  <div className="text-xs text-slate-400">טוען דירוג תובנות...</div>
                                )}
                                {filtered.map((contradiction, index) => (
                                  <ContradictionCard
                                    key={contradiction.id || index}
                                    contradiction={contradiction}
                                    index={index}
                                    onShowEvidence={handleShowEvidence}
                                    insight={insightsByContradiction[contradiction.id || '']}
                                  />
                                ))}
                              </>
                            );
                          })()}
                        </motion.div>
                      )}

                      {analysisResultsTab === 'questions' && (
                        <motion.div
                          key="questions"
                          initial={{ opacity: 0, x: 20 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: -20 }}
                          className="space-y-4"
                        >
                          {(() => {
                            // Extract questions from contradictions or metadata
                            const allQuestions: CrossExamQuestion[] = [];
                            selectedRun.contradictions?.forEach((c) => {
                              // If contradiction has questions, add them
                              const meta = c as any;
                              if (meta.cross_exam_questions) {
                                const flat = flattenCrossExamQuestions(meta.cross_exam_questions);
                                allQuestions.push(...flat);
                              }
                            });
                            // Also check metadata
                            const runMeta = selectedRun.metadata as any;
                            if (runMeta?.cross_exam_questions) {
                              const flat = flattenCrossExamQuestions(runMeta.cross_exam_questions);
                              allQuestions.push(...flat);
                            }

                            if (allQuestions.length === 0) {
                              return (
                                <Card>
                                  <div className="text-center py-8">
                                    <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                    <p className="text-lg font-medium text-slate-700">
                                      אין שאלות לחקירה נגדית
                                    </p>
                                    <p className="text-sm text-slate-500 mt-2">
                                      שאלות נוצרות כאשר מזוהות סתירות
                                    </p>
                                  </div>
                                </Card>
                              );
                            }

                            return allQuestions.map((question, index) => (
                              <QuestionCard
                                key={question.id || index}
                                question={question}
                                index={index}
                              />
                            ));
                          })()}
                        </motion.div>
                      )}

                      {analysisResultsTab === 'plan' && (
                        <motion.div
                          key="plan"
                          initial={{ opacity: 0, x: 20 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: -20 }}
                          className="space-y-4"
                        >
                          <div className="flex items-center gap-2">
                            <Button
                              onClick={handleGeneratePlan}
                              isLoading={isLoadingPlan}
                              variant="primary"
                            >
                              צור תכנית חקירה
                            </Button>
                            <select
                              value={simulationPersona}
                              onChange={(e) => setSimulationPersona(e.target.value as typeof simulationPersona)}
                              className="px-3 py-2 rounded-xl border-2 border-slate-200 bg-white text-slate-900 text-sm focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
                            >
                              <option value="cooperative">עד משתף פעולה</option>
                              <option value="evasive">עד מתחמק</option>
                              <option value="hostile">עד עוין</option>
                            </select>
                            <Button
                              onClick={handleSimulateWitness}
                              isLoading={isSimulating}
                              variant="secondary"
                              disabled={!crossExamPlan}
                            >
                              סימולציית עד
                            </Button>
                            <Button
                              onClick={() => handleExportPlan('docx')}
                              variant="ghost"
                              disabled={!crossExamPlan}
                            >
                              ייצוא DOCX
                            </Button>
                            <Button
                              onClick={() => handleExportPlan('pdf')}
                              variant="ghost"
                              disabled={!crossExamPlan}
                            >
                              ייצוא PDF
                            </Button>
                            {planError && (
                              <span className="text-sm text-danger-600">{planError}</span>
                            )}
                          </div>

                          {isLoadingPlan && (
                            <div className="flex items-center gap-2 text-sm text-slate-500">
                              <Spinner size="sm" />
                              טוען תכנית...
                            </div>
                          )}

                          {!isLoadingPlan && crossExamPlan && (
                            <div className="space-y-4">
                              {crossExamPlan.stages.map((stage) => (
                                <Card key={stage.stage}>
                                  <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                      <h4 className="font-semibold text-slate-900">
                                        שלב {stage.stage}
                                      </h4>
                                      <Badge variant="neutral">
                                        {stage.steps.length} צעדים
                                      </Badge>
                                    </div>
                                    <div className="space-y-3">
                                      {stage.steps.map((step) => (
                                        <PlanStepCard
                                          key={step.id}
                                          step={step}
                                          onShowEvidence={handleShowEvidenceAnchors}
                                        />
                                      ))}
                                    </div>
                                  </div>
                                </Card>
                              ))}
                            </div>
                          )}

                          {!isLoadingPlan && !crossExamPlan && !planError && (
                            <EmptyState
                              icon={<ListOrdered className="w-12 h-12" />}
                              title="אין תכנית חקירה"
                              description="לחץ על יצירת תכנית כדי לבנות תכנית מדורגת"
                            />
                          )}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                )}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'witnesses' && (
          <motion.div
            key="witnesses"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4"
          >
            <Card>
              <div className="space-y-4">
                <h3 className="font-semibold text-slate-900">הוספת עד</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Input
                    placeholder="שם העד"
                    value={newWitnessName}
                    onChange={(e) => setNewWitnessName(e.target.value)}
                  />
                  <select
                    value={newWitnessSide}
                    onChange={(e) => setNewWitnessSide(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
                  >
                    <option value="unknown">לא ידוע</option>
                    <option value="ours">שלנו</option>
                    <option value="theirs">של הצד שכנגד</option>
                  </select>
                  <Button
                    onClick={handleCreateWitness}
                    isLoading={isCreatingWitness}
                    disabled={!newWitnessName.trim()}
                  >
                    הוסף עד
                  </Button>
                </div>
                {witnessError && (
                  <div className="text-sm text-danger-600">{witnessError}</div>
                )}
              </div>
            </Card>

            {isLoadingWitnesses ? (
              <div className="flex items-center justify-center py-10">
                <Spinner size="lg" />
              </div>
            ) : witnesses.length === 0 ? (
              <EmptyState
                icon={<Users className="w-16 h-16" />}
                title="אין עדים עדיין"
                description="הוסף עד ראשון כדי להתחיל לעבוד על גרסאות"
              />
            ) : (
              <div className="space-y-4">
                {witnesses.map((witness) => (
                  <WitnessCard
                    key={witness.id}
                    witness={witness}
                    documents={documents}
                    onRefresh={fetchWitnesses}
                    onShowEvidence={handleShowEvidenceAnchors}
                  />
                ))}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'notes' && (
          <motion.div
            key="notes"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4"
          >
            {/* Add New Note */}
            <Card>
              <div className="space-y-3">
                <h3 className="font-semibold text-slate-900">הוסף הערה חדשה</h3>
                <textarea
                  value={newNoteText}
                  onChange={(e) => setNewNoteText(e.target.value)}
                  placeholder="כתבו הערה, ממצא חשוב, או משימה לביצוע..."
                  rows={3}
                  className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none resize-none"
                />
                <div className="flex justify-end">
                  <Button
                    onClick={handleAddNote}
                    disabled={!newNoteText.trim()}
                    isLoading={isSavingNotes}
                    leftIcon={<Plus className="w-4 h-4" />}
                  >
                    הוסף הערה
                  </Button>
                </div>
              </div>
            </Card>

            {/* Notes List */}
            {isLoadingNotes ? (
              <div className="flex items-center justify-center py-12">
                <Spinner size="lg" />
              </div>
            ) : notes.length === 0 ? (
              <EmptyState
                icon={<StickyNote className="w-16 h-16" />}
                title="אין הערות עדיין"
                description="הוסיפו הערות, ממצאים ומשימות לתיק"
              />
            ) : (
              <div className="space-y-3">
                {notes.map((note) => (
                  <Card key={note.id}>
                    {editingNoteId === note.id ? (
                      <div className="space-y-3">
                        <textarea
                          value={editingNoteText}
                          onChange={(e) => setEditingNoteText(e.target.value)}
                          rows={3}
                          className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none resize-none"
                        />
                        <div className="flex gap-2 justify-end">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              setEditingNoteId(null);
                              setEditingNoteText('');
                            }}
                          >
                            ביטול
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleUpdateNote(note.id)}
                            isLoading={isSavingNotes}
                            leftIcon={<Save className="w-4 h-4" />}
                          >
                            שמור
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <p className="text-slate-800 whitespace-pre-wrap">{note.text}</p>
                          <p className="text-xs text-slate-400 mt-2">
                            {new Date(note.created_at).toLocaleString('he-IL')}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditingNoteId(note.id);
                              setEditingNoteText(note.text);
                            }}
                          >
                            ערוך
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteNote(note.id)}
                            className="text-danger-600 hover:text-danger-700 hover:bg-danger-50"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'team' && (
          <motion.div
            key="team"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4"
          >
            {/* Header with Add Button */}
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900">משתתפים בתיק</h3>
              <Button
                onClick={() => setShowAddParticipantModal(true)}
                leftIcon={<UserPlus className="w-4 h-4" />}
              >
                הוסף משתתף
              </Button>
            </div>

            {/* Participants List */}
            {isLoadingParticipants ? (
              <div className="flex items-center justify-center py-12">
                <Spinner size="lg" />
              </div>
            ) : participants.length === 0 ? (
              <EmptyState
                icon={<Users className="w-16 h-16" />}
                title="אין משתתפים בתיק"
                description="הוסיפו משתמשים לתיק כדי לשתף אותם בעבודה"
                action={{
                  label: 'הוסף משתתף',
                  onClick: () => setShowAddParticipantModal(true),
                  icon: <UserPlus className="w-5 h-5" />,
                }}
              />
            ) : (
              <Card padding="none">
                <div className="divide-y divide-slate-100">
                  {participants.map((participant) => (
                    <div
                      key={participant.user_id}
                      className="p-4 flex items-center gap-4"
                    >
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-bold">
                        {participant.name?.charAt(0) || '?'}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-slate-900">{participant.name}</p>
                        <p className="text-sm text-slate-500 truncate">{participant.email}</p>
                      </div>
                      {participant.role && (
                        <Badge variant="neutral">{participant.role}</Badge>
                      )}
                      <p className="text-xs text-slate-400">
                        {new Date(participant.added_at).toLocaleDateString('he-IL')}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Add Participant Modal */}
      <Modal
        isOpen={showAddParticipantModal}
        onClose={() => {
          setShowAddParticipantModal(false);
          setNewParticipantEmail('');
          setNewParticipantRole('');
          setAddParticipantError('');
        }}
        title="הוספת משתתף לתיק"
        description="הזינו את כתובת הדוא״ל של המשתמש להוספה לתיק"
        size="md"
      >
        <div className="space-y-4">
          {addParticipantError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {addParticipantError}
            </div>
          )}

          <Input
            label="כתובת דוא״ל"
            type="email"
            value={newParticipantEmail}
            onChange={(e) => setNewParticipantEmail(e.target.value)}
            placeholder="user@example.com"
            leftIcon={<Mail className="w-5 h-5" />}
            required
          />

          <Input
            label="תפקיד (אופציונלי)"
            value={newParticipantRole}
            onChange={(e) => setNewParticipantRole(e.target.value)}
            placeholder="לדוגמה: עורך דין, עוזר משפטי"
          />

          <div className="flex gap-3 pt-4">
            <Button
              onClick={handleAddParticipant}
              className="flex-1"
              isLoading={isAddingParticipant}
              disabled={!newParticipantEmail.trim()}
            >
              הוסף לתיק
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setShowAddParticipantModal(false);
                setNewParticipantEmail('');
                setNewParticipantRole('');
              }}
            >
              ביטול
            </Button>
          </div>
        </div>
      </Modal>

      {/* Create Folder Modal */}
      <Modal
        isOpen={showCreateFolderModal}
        onClose={() => {
          setShowCreateFolderModal(false);
          setNewFolderName('');
          setNewFolderParentId(undefined);
          setCreateFolderError('');
        }}
        title="יצירת תיקייה חדשה"
        description="צרו תיקייה חדשה לארגון המסמכים"
        size="md"
      >
        <div className="space-y-4">
          {createFolderError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {createFolderError}
            </div>
          )}

          <Input
            label="שם התיקייה"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="לדוגמה: עדויות, מסמכי בית משפט"
            required
          />

          {folders.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                תיקיית אב (אופציונלי)
              </label>
              <select
                value={newFolderParentId || ''}
                onChange={(e) => setNewFolderParentId(e.target.value || undefined)}
                className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
              >
                <option value="">בחר תיקייה (שורש)</option>
                {folders.map((folder) => (
                  <option key={folder.id} value={folder.id}>
                    {folder.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex gap-3 pt-4">
            <Button
              onClick={handleCreateFolder}
              className="flex-1"
              isLoading={isCreatingFolder}
              disabled={!newFolderName.trim()}
            >
              צור תיקייה
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setShowCreateFolderModal(false);
                setNewFolderName('');
                setNewFolderParentId(undefined);
              }}
            >
              ביטול
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Folder Modal */}
      <Modal
        isOpen={showDeleteFolderModal}
        onClose={() => {
          setShowDeleteFolderModal(false);
          setFolderToDelete(null);
          setDeleteFolderError('');
          setDeleteFolderRecursive(false);
        }}
        title="מחיקת תיקייה"
        description="האם אתה בטוח שברצונך למחוק תיקייה זו?"
        size="sm"
      >
        <div className="space-y-4">
          {deleteFolderError && (
            <div className="p-4 rounded-xl bg-danger-50 border border-danger-200 text-danger-700 text-sm">
              {deleteFolderError}
            </div>
          )}

          <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl">
            <p className="text-sm text-amber-800">
              שים לב: אם התיקייה מכילה מסמכים או תיקיות משנה, תצטרך לסמן את האפשרות למחיקה רקורסיבית.
            </p>
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={deleteFolderRecursive}
              onChange={(e) => setDeleteFolderRecursive(e.target.checked)}
              className="w-4 h-4 text-danger-600 rounded focus:ring-danger-500"
            />
            <span className="text-sm text-slate-700">
              מחק תוכן רקורסיבית (כולל מסמכים ותיקיות משנה)
            </span>
          </label>

          <div className="flex gap-3 pt-4">
            <Button
              variant="danger"
              onClick={handleDeleteFolder}
              className="flex-1"
              isLoading={isDeletingFolder}
            >
              מחק תיקייה
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setShowDeleteFolderModal(false);
                setFolderToDelete(null);
              }}
            >
              ביטול
            </Button>
          </div>
        </div>
      </Modal>

      {/* Document Preview Modal */}
      <Modal
        isOpen={showPreviewModal}
        onClose={() => {
          setShowPreviewModal(false);
          setPreviewDoc(null);
          setPreviewText('');
        }}
        title={previewDoc?.doc_name || 'תצוגה מקדימה'}
        description={previewDoc ? `${previewDoc.page_count || 0} עמודים • ${previewDoc.party || 'לא מוגדר'}` : ''}
        size="lg"
      >
        <div className="space-y-4">
          {/* Document info bar */}
          {previewDoc && (
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{getFileIcon(previewDoc.mime_type)}</span>
                <div>
                  <p className="text-sm font-medium text-slate-900">{previewDoc.doc_name}</p>
                  <p className="text-xs text-slate-500">
                    {new Date(previewDoc.created_at).toLocaleDateString('he-IL')}
                  </p>
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setShowPreviewModal(false);
                  navigate(`/documents/${previewDoc.id}`);
                }}
              >
                פתח בדף מלא
              </Button>
            </div>
          )}

          {/* Text content */}
          {isLoadingPreview ? (
            <div className="flex items-center justify-center py-12">
              <Spinner size="lg" />
              <span className="mr-3 text-slate-600">טוען טקסט...</span>
            </div>
          ) : previewText ? (
            <div className="bg-slate-50 rounded-xl p-6 max-h-[500px] overflow-y-auto">
              <pre className="whitespace-pre-wrap font-sans text-sm text-slate-700 leading-relaxed" dir="auto">
                {previewText}
              </pre>
            </div>
          ) : (
            <div className="text-center py-12 text-slate-500">
              <FileText className="w-12 h-12 mx-auto mb-4 text-slate-300" />
              <p>אין טקסט זמין במסמך זה</p>
            </div>
          )}

          {/* Character count */}
          {previewText && (
            <p className="text-xs text-slate-400 text-left">
              {previewText.length.toLocaleString()} תווים
            </p>
          )}
        </div>
      </Modal>

      {/* Upload Modal */}
      <Modal
        isOpen={showUploadModal}
        onClose={() => {
          setShowUploadModal(false);
          setUploadFiles([]);
          setUploadFolderId(undefined);
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

          {/* Folder selection */}
          {folders.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                העלה לתיקייה (אופציונלי)
              </label>
              <select
                value={uploadFolderId || ''}
                onChange={(e) => setUploadFolderId(e.target.value || undefined)}
                className="w-full px-4 py-3 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
              >
                <option value="">שורש התיק</option>
                {folders.map((folder) => (
                  <option key={folder.id} value={folder.id}>
                    {folder.name}
                  </option>
                ))}
              </select>
            </div>
          )}

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

      {/* Analysis Options Modal */}
      <Modal
        isOpen={showAnalysisModal}
        onClose={() => setShowAnalysisModal(false)}
        title="אפשרויות ניתוח"
        description="בחרו את סוג הניתוח והמסמכים לניתוח"
        size="lg"
      >
        <div className="space-y-6">
          {/* Analysis Mode */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-3">
              מצב ניתוח
            </label>
            <div className="grid grid-cols-3 gap-3">
              <button
                onClick={() => setAnalysisMode('hybrid')}
                className={`p-4 rounded-xl border-2 transition-colors text-center ${
                  analysisMode === 'hybrid'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="font-medium text-slate-900">היברידי</div>
                <p className="text-xs text-slate-500 mt-1">חוקים + AI (מומלץ)</p>
              </button>
              <button
                onClick={() => setAnalysisMode('rule_based')}
                className={`p-4 rounded-xl border-2 transition-colors text-center ${
                  analysisMode === 'rule_based'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="font-medium text-slate-900">חוקים</div>
                <p className="text-xs text-slate-500 mt-1">מהיר יותר</p>
              </button>
              <button
                onClick={() => setAnalysisMode('llm')}
                className={`p-4 rounded-xl border-2 transition-colors text-center ${
                  analysisMode === 'llm'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="font-medium text-slate-900">AI בלבד</div>
                <p className="text-xs text-slate-500 mt-1">מדויק יותר</p>
              </button>
            </div>
          </div>

          {/* Document Selection */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-3">
              מסמכים לניתוח
            </label>
            <div className="max-h-48 overflow-y-auto border-2 border-slate-200 rounded-xl p-2 space-y-1">
              <button
                onClick={() => setSelectedDocIds([])}
                className={`w-full text-right p-3 rounded-lg transition-colors ${
                  selectedDocIds.length === 0
                    ? 'bg-primary-50 text-primary-700'
                    : 'hover:bg-slate-50 text-slate-700'
                }`}
              >
                <div className="font-medium">כל המסמכים ({documents.length})</div>
              </button>
              {documents.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => {
                    if (selectedDocIds.includes(doc.id)) {
                      setSelectedDocIds(selectedDocIds.filter(id => id !== doc.id));
                    } else {
                      setSelectedDocIds([...selectedDocIds, doc.id]);
                    }
                  }}
                  className={`w-full text-right p-3 rounded-lg transition-colors flex items-center gap-3 ${
                    selectedDocIds.includes(doc.id)
                      ? 'bg-primary-50 text-primary-700'
                      : 'hover:bg-slate-50 text-slate-700'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedDocIds.includes(doc.id)}
                    onChange={() => {}}
                    className="w-4 h-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                  />
                  <div className="flex-1">
                    <div className="font-medium truncate">{doc.doc_name || doc.original_filename}</div>
                    <div className="text-xs text-slate-500">{doc.page_count} עמודים</div>
                  </div>
                </button>
              ))}
            </div>
            {selectedDocIds.length > 0 && (
              <p className="text-sm text-primary-600 mt-2">
                נבחרו {selectedDocIds.length} מסמכים
              </p>
            )}
          </div>

          {/* Force Reanalyze */}
          <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
            <div>
              <p className="font-medium text-slate-900">כפה ניתוח מחדש</p>
              <p className="text-sm text-slate-500">התעלם מתוצאות קודמות במטמון</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={forceReanalyze}
                onChange={(e) => setForceReanalyze(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-300 peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
            </label>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <Button
              onClick={handleAnalyze}
              className="flex-1"
              leftIcon={<Play className="w-5 h-5" />}
            >
              הפעל ניתוח
            </Button>
            <Button
              variant="secondary"
              onClick={() => setShowAnalysisModal(false)}
            >
              ביטול
            </Button>
          </div>
        </div>
      </Modal>

      <EvidenceViewerModal
        isOpen={isEvidenceViewerOpen}
        onClose={() => setIsEvidenceViewerOpen(false)}
        leftAnchor={evidenceLeftAnchor}
        rightAnchor={evidenceRightAnchor}
      />

      <Modal
        isOpen={isSimulationModalOpen}
        onClose={() => setIsSimulationModalOpen(false)}
        title="סימולציית עד"
        size="lg"
      >
        {simulationResult ? (
          <div className="space-y-4">
            <div className="text-sm text-slate-500">
              פרסונה: {simulationResult.persona}
            </div>
            {simulationResult.steps.map((step, idx) => (
              <Card key={`${step.step_id}_${idx}`}>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant="neutral">{step.stage}</Badge>
                    <span className="text-slate-700">{step.question}</span>
                  </div>
                  <div className="text-slate-900 font-medium">תשובת העד: {step.witness_reply}</div>
                  {step.chosen_branch_trigger && (
                    <div className="text-xs text-slate-500">
                      הסתעפות: {step.chosen_branch_trigger}
                    </div>
                  )}
                  {step.follow_up_questions && step.follow_up_questions.length > 0 && (
                    <ul className="list-disc list-inside text-xs text-slate-600">
                      {step.follow_up_questions.map((q, qIdx) => (
                        <li key={`${qIdx}-${q}`}>{q}</li>
                      ))}
                    </ul>
                  )}
                  {step.warnings && step.warnings.length > 0 && (
                    <div className="text-xs text-danger-600 space-y-1">
                      {step.warnings.map((w, wIdx) => (
                        <div key={`${wIdx}-${w}`}>{w}</div>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<MessageSquare className="w-12 h-12" />}
            title="אין סימולציה"
            description="צור תכנית ואז הפעל סימולציה."
          />
        )}
      </Modal>
    </div>
  );
};

// Folder Tree Item Component
const FolderTreeItem: React.FC<{
  folder: FolderType;
  selectedFolderId: string | undefined;
  onSelect: (folderId: string | undefined) => void;
  onDelete: (folderId: string) => void;
  level: number;
}> = ({ folder, selectedFolderId, onSelect, onDelete, level }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = folder.children && folder.children.length > 0;

  return (
    <div>
      <div
        className={`group w-full flex items-center gap-2 p-2 rounded-lg transition-colors ${
          selectedFolderId === folder.id
            ? 'bg-primary-50 text-primary-700'
            : 'hover:bg-slate-50 text-slate-700'
        }`}
        style={{ paddingRight: `${8 + level * 16}px` }}
      >
        {hasChildren && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="p-0.5 hover:bg-slate-200 rounded"
          >
            {isExpanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronLeft className="w-3 h-3" />
            )}
          </button>
        )}
        <button
          onClick={() => onSelect(folder.id)}
          className="flex-1 flex items-center gap-2 min-w-0"
        >
          <Folder className="w-4 h-4 text-amber-500 flex-shrink-0" />
          <span className="text-sm font-medium truncate">{folder.name}</span>
          {folder.document_count !== undefined && folder.document_count > 0 && (
            <span className="text-xs text-slate-400">({folder.document_count})</span>
          )}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(folder.id);
          }}
          className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-danger-600 rounded transition-all"
          title="מחק תיקייה"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      {hasChildren && isExpanded && (
        <div className="space-y-1">
          {folder.children!.map((child) => (
            <FolderTreeItem
              key={child.id}
              folder={child}
              selectedFolderId={selectedFolderId}
              onSelect={onSelect}
              onDelete={onDelete}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// Witness Card Component
const WitnessCard: React.FC<{
  witness: Witness;
  documents: DocumentType[];
  onRefresh: () => void;
  onShowEvidence: (left?: EvidenceAnchor | null, right?: EvidenceAnchor | null) => void;
}> = ({ witness, documents, onRefresh, onShowEvidence }) => {
  const versions = witness.versions || [];
  const [versionDocId, setVersionDocId] = useState('');
  const [versionType, setVersionType] = useState('');
  const [versionDate, setVersionDate] = useState('');
  const [isSavingVersion, setIsSavingVersion] = useState(false);
  const [diffA, setDiffA] = useState('');
  const [diffB, setDiffB] = useState('');
  const [diffResult, setDiffResult] = useState<WitnessVersionDiffResponse | null>(null);
  const [isDiffLoading, setIsDiffLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (versions.length >= 2 && (!diffA || !diffB)) {
      setDiffA(versions[0].id);
      setDiffB(versions[1].id);
    }
  }, [versions, diffA, diffB]);

  const handleAddVersion = async () => {
    if (!versionDocId) return;
    setIsSavingVersion(true);
    setError('');
    try {
      await witnessesApi.createVersion(witness.id, {
        document_id: versionDocId,
        version_type: versionType || undefined,
        version_date: versionDate || undefined,
      });
      setVersionDocId('');
      setVersionType('');
      setVersionDate('');
      await onRefresh();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsSavingVersion(false);
    }
  };

  const handleDiff = async () => {
    if (!diffA || !diffB || diffA === diffB) return;
    setIsDiffLoading(true);
    setError('');
    try {
      const res = await witnessesApi.diffVersions(witness.id, {
        version_a_id: diffA,
        version_b_id: diffB,
      });
      setDiffResult(res);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsDiffLoading(false);
    }
  };

  const getShiftLabel = (shiftType: string) => {
    const map: Record<string, string> = {
      low_similarity: 'דמיון נמוך',
      time_change: 'שינוי במועדים',
      entity_change: 'שינוי בישויות',
      negation_flip: 'היפוך שלילה',
    };
    return map[shiftType] || shiftType;
  };

  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-semibold text-slate-900">{witness.name}</h4>
            <p className="text-xs text-slate-500">
              צד: {witness.side || 'לא ידוע'}
            </p>
          </div>
          <Badge variant="neutral">{versions.length} גרסאות</Badge>
        </div>

        {error && <div className="text-sm text-danger-600">{error}</div>}

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select
            value={versionDocId}
            onChange={(e) => setVersionDocId(e.target.value)}
            className="w-full px-4 py-2 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
          >
            <option value="">בחר מסמך לגרסה</option>
            {documents.map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.doc_name || doc.original_filename || doc.id}
              </option>
            ))}
          </select>
          <Input
            placeholder="סוג גרסה (למשל: תצהיר)"
            value={versionType}
            onChange={(e) => setVersionType(e.target.value)}
          />
          <Input
            type="date"
            value={versionDate}
            onChange={(e) => setVersionDate(e.target.value)}
          />
          <Button
            variant="secondary"
            onClick={handleAddVersion}
            isLoading={isSavingVersion}
            disabled={!versionDocId}
          >
            הוסף גרסה
          </Button>
        </div>

        {versions.length > 0 && (
          <div className="space-y-2">
            {versions.map((v) => (
              <div key={v.id} className="flex items-center justify-between text-sm text-slate-700">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{v.document_name || v.document_id}</span>
                  {v.version_type && <Badge variant="neutral">{v.version_type}</Badge>}
                </div>
                {v.version_date && (
                  <span className="text-xs text-slate-500">
                    {new Date(v.version_date).toLocaleDateString('he-IL')}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {versions.length >= 2 && (
          <div className="border-t border-slate-100 pt-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <select
                value={diffA}
                onChange={(e) => setDiffA(e.target.value)}
                className="w-full px-4 py-2 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.document_name || v.document_id}
                  </option>
                ))}
              </select>
              <select
                value={diffB}
                onChange={(e) => setDiffB(e.target.value)}
                className="w-full px-4 py-2 rounded-xl border-2 border-slate-200 bg-white text-slate-900 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/10 focus:outline-none"
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.document_name || v.document_id}
                  </option>
                ))}
              </select>
              <Button onClick={handleDiff} isLoading={isDiffLoading} disabled={!diffA || !diffB || diffA === diffB}>
                השווה גרסאות
              </Button>
            </div>

            {diffResult && (
              <div className="space-y-3">
                <p className="text-sm text-slate-500">
                  דמיון כללי: {Math.round(diffResult.similarity * 100)}%
                </p>
                {diffResult.shifts.length === 0 ? (
                  <EmptyState
                    icon={<CheckCircle className="w-10 h-10" />}
                    title="לא זוהו שינויים מהותיים"
                    description="הגרסאות דומות ברמת הנרטיב"
                  />
                ) : (
                  diffResult.shifts.map((shift, idx) => (
                    <div key={`${shift.shift_type}_${idx}`} className="border border-slate-200 rounded-xl p-3">
                      <div className="flex items-center justify-between">
                        <Badge variant="warning">{getShiftLabel(shift.shift_type)}</Badge>
                        {shift.similarity !== undefined && (
                          <span className="text-xs text-slate-500">
                            {Math.round(shift.similarity * 100)}%
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-700 mt-2">{shift.description}</p>
                      {shift.details && (
                        <pre className="text-xs text-slate-500 bg-slate-50 rounded-lg p-2 mt-2 whitespace-pre-wrap">
                          {JSON.stringify(shift.details, null, 2)}
                        </pre>
                      )}
                      {shift.anchor_a && shift.anchor_b && (
                        <div className="mt-2 flex justify-end">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => onShowEvidence(shift.anchor_a, shift.anchor_b)}
                          >
                            הצג ראיות
                          </Button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
};

const PlanStepCard: React.FC<{
  step: CrossExamPlanStep;
  onShowEvidence: (left?: EvidenceAnchor | null, right?: EvidenceAnchor | null) => void;
}> = ({ step, onShowEvidence }) => {
  const anchors = step.anchors || [];
  const left = anchors[0] || null;
  const right = anchors[1] || null;

  return (
    <div className="border border-slate-200 rounded-xl p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="neutral">{step.step_type}</Badge>
          <span className="text-sm font-medium text-slate-900">{step.title}</span>
        </div>
        {step.do_not_ask_flag && (
          <Badge variant="danger">DON'T ASK</Badge>
        )}
      </div>
      {step.do_not_ask_flag && step.do_not_ask_reason && (
        <div className="text-xs text-danger-700 bg-danger-50 border border-danger-200 rounded-lg p-2">
          {step.do_not_ask_reason}
        </div>
      )}
      <div className="text-sm text-slate-700">{step.question}</div>
      {step.branches && step.branches.length > 0 && (
        <div className="text-xs text-slate-600 space-y-2">
          <div className="font-medium text-slate-700">הסתעפויות:</div>
          {step.branches.map((branch, idx) => (
            <div key={`${branch.trigger}_${idx}`} className="pl-3 border-r-2 border-slate-200">
              <div>{branch.trigger}</div>
              {branch.follow_up_questions?.length > 0 && (
                <ul className="list-disc list-inside mt-1">
                  {branch.follow_up_questions.map((q, qIdx) => (
                    <li key={`${qIdx}-${q}`} className="text-slate-600">
                      {q}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
      {left && right && (
        <div className="flex justify-end">
          <Button size="sm" variant="secondary" onClick={() => onShowEvidence(left, right)}>
            הצג ראיות
          </Button>
        </div>
      )}
    </div>
  );
};

// Contradiction Card Component
const ContradictionCard: React.FC<{
  contradiction: Contradiction;
  index: number;
  onShowEvidence: (contradiction: Contradiction) => void;
  insight?: ContradictionInsight;
}> = ({ contradiction, index, onShowEvidence, insight }) => {
  const navigate = useNavigate();
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
      case 'high':
        return 'danger';
      case 'medium':
        return 'warning';
      default:
        return 'neutral';
    }
  };

  const getSeverityLabel = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'קריטי';
      case 'high':
        return 'גבוה';
      case 'medium':
        return 'בינוני';
      case 'low':
        return 'נמוך';
      default:
        return severity;
    }
  };

  const getTypeLabel = (type: string) => {
    const types: Record<string, string> = {
      'TEMPORAL_DATE': 'סתירה בתאריכים',
      'QUANTITATIVE_AMOUNT': 'סתירה בכמויות/סכומים',
      'ACTOR_ATTRIBUTION': 'סתירה בזיהוי מבצע הפעולה',
      'PRESENCE_PARTICIPATION': 'סתירה בנוכחות/השתתפות',
      'DOCUMENT_EXISTENCE': 'סתירה בקיום מסמך',
      'IDENTITY_BASIC': 'סתירה בזיהוי/זהות',
    };
    return types[type] || type;
  };

  const getExplanation = () => {
    if (contradiction.explanation_he) return contradiction.explanation_he;
    if (contradiction.explanation) return contradiction.explanation;

    const explanations: Record<string, string> = {
      'TEMPORAL_DATE': `התאריכים בשתי הטענות אינם תואמים. יש לברר איזה תאריך הוא הנכון.`,
      'QUANTITATIVE_AMOUNT': `הכמויות או הסכומים המצוינים בשתי הטענות שונים זה מזה.`,
      'ACTOR_ATTRIBUTION': `יש אי-התאמה לגבי מי ביצע את הפעולה המתוארת.`,
      'PRESENCE_PARTICIPATION': `הטענות סותרות זו את זו לגבי נוכחות או השתתפות במאורע.`,
      'DOCUMENT_EXISTENCE': `יש סתירה לגבי קיומו או אי-קיומו של מסמך.`,
      'IDENTITY_BASIC': `פרטי הזיהוי בשתי הטענות אינם תואמים.`,
    };

    const key = contradiction.contradiction_type || contradiction.type || '';
    return explanations[key] ||
      `שתי הטענות מכילות מידע סותר שדורש בירור נוסף.`;
  };

  const severity = contradiction.severity || 'medium';
  const contradictionType = contradiction.contradiction_type || contradiction.type || 'unknown';

  const claimAText =
    contradiction.claim_a?.text || contradiction.claim1_text || contradiction.quote1 || 'לא זמין';
  const claimBText =
    contradiction.claim_b?.text || contradiction.claim2_text || contradiction.quote2 || 'לא זמין';
  const hasEvidence = Boolean(
    (toEvidenceAnchor(contradiction.claim1_locator) || anchorFromClaim(contradiction.claim_a)) &&
      (toEvidenceAnchor(contradiction.claim2_locator) || anchorFromClaim(contradiction.claim_b))
  );

  const renderScore = (value?: number) => {
    if (value === undefined || value === null) return '—';
    return `${Math.round(value * 100)}%`;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
    >
      <Card className="border-r-4 border-warning-500">
        <div className="space-y-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-warning-500" />
              <span className="font-bold text-slate-900">סתירה #{index + 1}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={getSeverityColor(severity) as any}>
                {getSeverityLabel(severity)}
              </Badge>
              <Badge variant="neutral">{getTypeLabel(contradictionType)}</Badge>
            </div>
          </div>

          {/* Claims */}
          <div className="space-y-3">
            <div className="p-4 bg-red-50 rounded-xl border border-red-100">
              <div className="text-xs text-red-500 font-medium mb-1">טענה א'</div>
              <p className="text-slate-800">{claimAText}</p>
              {contradiction.claim_a?.source_name && (
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs text-slate-500">מקור:</span>
                  {contradiction.claim_a.source_doc_id ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        const params = new URLSearchParams();
                        if (contradiction.claim_a?.page_no) {
                          params.set('page', String(contradiction.claim_a.page_no));
                        }
                        if (contradiction.claim_a?.block_index !== undefined) {
                          params.set('block', String(contradiction.claim_a.block_index));
                        }
                        const query = params.toString() ? `?${params.toString()}` : '';
                        const docId = contradiction.claim_a?.source_doc_id;
                        if (docId) navigate(`/documents/${docId}${query}`);
                      }}
                      className="text-xs text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1 hover:underline"
                    >
                      {contradiction.claim_a.source_name}
                      {contradiction.claim_a.page_no && (
                        <span className="text-slate-400">(עמ' {contradiction.claim_a.page_no})</span>
                      )}
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  ) : (
                    <span className="text-xs text-slate-500">{contradiction.claim_a.source_name}</span>
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-center">
              <div className="w-8 h-8 rounded-full bg-warning-100 flex items-center justify-center">
                <ArrowDown className="w-4 h-4 text-warning-600" />
              </div>
            </div>

            <div className="p-4 bg-orange-50 rounded-xl border border-orange-100">
              <div className="text-xs text-orange-500 font-medium mb-1">טענה ב'</div>
              <p className="text-slate-800">{claimBText}</p>
              {contradiction.claim_b?.source_name && (
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs text-slate-500">מקור:</span>
                  {contradiction.claim_b.source_doc_id ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        const params = new URLSearchParams();
                        if (contradiction.claim_b?.page_no) {
                          params.set('page', String(contradiction.claim_b.page_no));
                        }
                        if (contradiction.claim_b?.block_index !== undefined) {
                          params.set('block', String(contradiction.claim_b.block_index));
                        }
                        const query = params.toString() ? `?${params.toString()}` : '';
                        const docId = contradiction.claim_b?.source_doc_id;
                        if (docId) navigate(`/documents/${docId}${query}`);
                      }}
                      className="text-xs text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1 hover:underline"
                    >
                      {contradiction.claim_b.source_name}
                      {contradiction.claim_b.page_no && (
                        <span className="text-slate-400">(עמ' {contradiction.claim_b.page_no})</span>
                      )}
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  ) : (
                    <span className="text-xs text-slate-500">{contradiction.claim_b.source_name}</span>
                  )}
                </div>
              )}
            </div>
          </div>

          {hasEvidence && (
            <div className="flex justify-end">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onShowEvidence(contradiction)}
              >
                השווה ראיות
              </Button>
            </div>
          )}

          {insight && (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
              <div className="flex flex-wrap gap-2 text-xs text-slate-600">
                <Badge variant="neutral">השפעה: {renderScore(insight.impact_score)}</Badge>
                <Badge variant="neutral">סיכון: {renderScore(insight.risk_score)}</Badge>
                <Badge variant="neutral">אימות: {renderScore(insight.verifiability_score)}</Badge>
                {insight.stage_recommendation && (
                  <Badge variant="warning">שלב: {insight.stage_recommendation}</Badge>
                )}
              </div>
              {insight.do_not_ask_flag && (
                <div className="text-sm text-danger-700 bg-danger-50 border border-danger-200 rounded-lg p-2">
                  <strong>אל תשאל/י זאת:</strong>{' '}
                  {insight.do_not_ask_reason || 'סיכון גבוה לעומת אחיזה חלשה בעוגנים.'}
                </div>
              )}
            </div>
          )}

          {/* Explanation */}
          <div className="p-4 bg-slate-50 rounded-xl">
            <div className="text-xs text-slate-500 font-medium mb-1">הסבר</div>
            <p className="text-slate-700">{getExplanation()}</p>
          </div>

          {/* Confidence */}
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span>רמת ביטחון:</span>
            <div className="flex-1 h-2 bg-slate-200 rounded-full max-w-32">
              <div
                className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full"
                style={{ width: `${(contradiction.confidence || 0) * 100}%` }}
              />
            </div>
            <span className="font-medium">
              {Math.round((contradiction.confidence || 0) * 100)}%
            </span>
          </div>
        </div>
      </Card>
    </motion.div>
  );
};

// Question Card Component
const QuestionCard: React.FC<{
  question: CrossExamQuestion;
  index: number;
}> = ({ question, index }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(question.question);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
    >
      <Card>
        <div className="space-y-3">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-600 font-bold text-sm">
                {index + 1}
              </div>
              <span className="text-xs text-slate-500">{question.strategy || 'שאלה'}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopy}
              leftIcon={copied ? <CheckCircle className="w-4 h-4 text-success-500" /> : <Copy className="w-4 h-4" />}
            >
              {copied ? 'הועתק!' : 'העתק'}
            </Button>
          </div>

          <p className="text-lg text-slate-900 font-medium">{question.question}</p>

          {question.purpose && (
            <p className="text-sm text-slate-500">
              <span className="font-medium">מטרה:</span> {question.purpose}
            </p>
          )}

          {(question.follow_up || (question.follow_ups && question.follow_ups.length > 0)) && (
            <div className="pt-3 border-t border-slate-100">
              <p className="text-xs text-slate-500 font-medium mb-2">שאלות המשך:</p>
              <ul className="space-y-1">
                {question.follow_up && (
                  <li className="text-sm text-slate-600 flex items-start gap-2">
                    <span className="text-slate-400">•</span>
                    {question.follow_up}
                  </li>
                )}
                {question.follow_ups?.map((followUp, i) => (
                  <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                    <span className="text-slate-400">•</span>
                    {followUp}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Card>
    </motion.div>
  );
};

export default CaseDetailPage;
