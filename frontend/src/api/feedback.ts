import apiClient from './client';
import type { FeedbackListResponse, FeedbackItem } from '../types';

export interface FeedbackCreateRequest {
  case_id: string;
  entity_type: 'insight' | 'plan_step';
  entity_id: string;
  label: 'worked' | 'not_worked' | 'too_risky' | 'excellent';
  note?: string;
}

export const feedbackApi = {
  list: async (caseId: string, entityType?: 'insight' | 'plan_step'): Promise<FeedbackListResponse> => {
    const response = await apiClient.get<FeedbackListResponse>('/api/v1/feedback', {
      params: { case_id: caseId, entity_type: entityType },
    });
    return response.data;
  },
  create: async (payload: FeedbackCreateRequest): Promise<FeedbackItem> => {
    const response = await apiClient.post<FeedbackItem>('/api/v1/feedback', payload);
    return response.data;
  },
};

export default feedbackApi;
