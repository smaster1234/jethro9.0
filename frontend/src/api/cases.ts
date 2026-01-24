import apiClient from './client';
import type { Case, CreateCaseRequest, Team, AnalysisRun, AnalysisResponse } from '../types';

export interface AnalyzeCaseOptions {
  document_ids?: string[];
  mode?: 'rule_based' | 'llm' | 'hybrid';
  force?: boolean;
  rag_top_k?: number;
}

export interface MemoryItem {
  id: string;
  text: string;
  created_at: string;
  type?: 'note' | 'finding' | 'todo';
}

export interface CaseParticipant {
  user_id: string;
  name: string;
  email: string;
  role?: string;
  added_at: string;
}

export const casesApi = {
  // List all cases
  list: async (): Promise<Case[]> => {
    const response = await apiClient.get<Case[]>('/cases');
    return response.data;
  },

  // List my accessible cases
  listMyCases: async (status?: string): Promise<Case[]> => {
    const response = await apiClient.get<Case[]>('/my/cases', {
      params: status ? { status } : undefined,
    });
    return response.data;
  },

  // Get case by ID
  get: async (caseId: string): Promise<Case> => {
    const response = await apiClient.get<Case>(`/cases/${caseId}`);
    return response.data;
  },

  // Create new case
  create: async (data: CreateCaseRequest): Promise<Case> => {
    const response = await apiClient.post<Case>('/cases', data);
    return response.data;
  },

  // Analyze case documents
  analyze: async (
    caseId: string,
    options?: AnalyzeCaseOptions
  ): Promise<AnalysisResponse & { cached?: boolean; run_id?: string }> => {
    const response = await apiClient.post(`/cases/${caseId}/analyze`, options);
    return response.data;
  },

  // Get teams assigned to case
  getTeams: async (caseId: string): Promise<Team[]> => {
    const response = await apiClient.get<Team[]>(`/cases/${caseId}/teams`);
    return response.data;
  },

  // Assign team to case
  assignTeam: async (caseId: string, teamId: string): Promise<void> => {
    await apiClient.post(`/cases/${caseId}/teams`, null, {
      params: { team_id: teamId },
    });
  },

  // List analysis runs
  listRuns: async (caseId: string, limit = 20): Promise<AnalysisRun[]> => {
    const response = await apiClient.get<AnalysisRun[]>(`/api/v1/cases/${caseId}/runs`, {
      params: { limit },
    });
    return response.data;
  },

  // Get analysis run details
  getRun: async (runId: string): Promise<AnalysisRun> => {
    const response = await apiClient.get<AnalysisRun>(`/api/v1/analysis-runs/${runId}`);
    return response.data;
  },

  // Get case memory/notes
  getMemory: async (caseId: string): Promise<MemoryItem[]> => {
    const response = await apiClient.get<{ memory: MemoryItem[] }>(`/cases/${caseId}/memory`);
    return response.data.memory || [];
  },

  // Save case memory/notes
  saveMemory: async (caseId: string, memory: MemoryItem[]): Promise<void> => {
    await apiClient.post(`/cases/${caseId}/memory`, { memory });
  },

  // List case participants
  getParticipants: async (caseId: string): Promise<CaseParticipant[]> => {
    const response = await apiClient.get<CaseParticipant[]>(`/cases/${caseId}/participants`);
    return response.data;
  },

  // Add participant to case
  addParticipant: async (caseId: string, userId: string, role?: string): Promise<CaseParticipant> => {
    const response = await apiClient.post<CaseParticipant>(`/cases/${caseId}/participants`, null, {
      params: { user_id: userId, role },
    });
    return response.data;
  },
};

export default casesApi;
