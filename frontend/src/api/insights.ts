import apiClient from './client';
import type { ContradictionInsight } from '../types';

export const insightsApi = {
  listByRun: async (runId: string): Promise<ContradictionInsight[]> => {
    const response = await apiClient.get<ContradictionInsight[]>(`/api/v1/analysis-runs/${runId}/insights`);
    return response.data;
  },
};

export default insightsApi;
