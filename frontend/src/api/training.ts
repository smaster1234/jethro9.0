import apiClient from './client';
import type { TrainingSession, TrainingTurn, TrainingSummary } from '../types';

export interface TrainingStartRequest {
  plan_id: string;
  witness_id?: string;
  persona?: string;
}

export interface TrainingTurnRequest {
  step_id: string;
  chosen_branch?: string;
}

export const trainingApi = {
  start: async (caseId: string, payload: TrainingStartRequest): Promise<TrainingSession> => {
    const response = await apiClient.post<TrainingSession>(`/api/v1/cases/${caseId}/training/start`, payload);
    return response.data;
  },
  turn: async (sessionId: string, payload: TrainingTurnRequest): Promise<TrainingTurn> => {
    const response = await apiClient.post<TrainingTurn>(`/api/v1/training/${sessionId}/turn`, payload);
    return response.data;
  },
  back: async (sessionId: string): Promise<{ session_id: string; back_remaining: number; removed_turn_id?: string }> => {
    const response = await apiClient.post(`/api/v1/training/${sessionId}/back`);
    return response.data;
  },
  finish: async (sessionId: string): Promise<{ session_id: string; summary: TrainingSummary }> => {
    const response = await apiClient.post(`/api/v1/training/${sessionId}/finish`);
    return response.data;
  },
};

export default trainingApi;
