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

// Health check
import apiClient from './client';
import type { HealthResponse } from '../types';

export const healthApi = {
  check: async (): Promise<HealthResponse> => {
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data;
  },
};
