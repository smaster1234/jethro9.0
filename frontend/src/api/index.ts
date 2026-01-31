export { default as apiClient, setTokens, clearTokens, getAccessToken, handleApiError } from './client';
export { default as authApi } from './auth';
export { default as casesApi } from './cases';
export { default as documentsApi } from './documents';
export { default as analysisApi } from './analysis';
export { default as orgsApi } from './orgs';
export { default as anchorsApi } from './anchors';
export { default as witnessesApi } from './witnesses';
export { default as insightsApi } from './insights';
export { default as crossExamPlanApi } from './crossExamPlan';
export { default as trainingApi } from './training';
export { default as usageApi } from './usage';
export { default as feedbackApi } from './feedback';
export { default as creditsApi } from './credits';
export type { UserCreditsInfo, CreditTransaction } from './credits';

// Health check
import apiClient from './client';
import type { HealthResponse } from '../types';

export const healthApi = {
  check: async (): Promise<HealthResponse> => {
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data;
  },
};

// Stats
export interface StatsOverview {
  cases_total: number;
  cases_active: number;
  documents_total: number;
  contradictions_total: number;
  analysis_runs_total: number;
  latest_run_at: string | null;
  jobs_active: number;
}

export const statsApi = {
  overview: async (): Promise<StatsOverview> => {
    const response = await apiClient.get<StatsOverview>('/api/v1/stats/overview');
    return response.data;
  },
};
