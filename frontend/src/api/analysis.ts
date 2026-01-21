import apiClient from './client';
import type { AnalysisResponse, CrossExamTrack, Claim } from '../types';

export interface AnalyzeTextRequest {
  text: string;
  source_name?: string;
}

export interface AnalyzeClaimsRequest {
  claims: Claim[];
}

export interface CrossExamTracksResponse {
  cross_exam_tracks: CrossExamTrack[];
  total_tracks: number;
  metadata?: Record<string, unknown>;
}

export const analysisApi = {
  // Analyze free text
  analyzeText: async (data: AnalyzeTextRequest): Promise<AnalysisResponse> => {
    const response = await apiClient.post<AnalysisResponse>('/analyze', data);
    return response.data;
  },

  // Analyze pre-extracted claims
  analyzeClaims: async (data: AnalyzeClaimsRequest): Promise<AnalysisResponse> => {
    const response = await apiClient.post<AnalysisResponse>('/analyze_claims', data);
    return response.data;
  },

  // Analyze with cross-exam tracks
  analyzeWithTracks: async (
    data: AnalyzeTextRequest
  ): Promise<{ analysis: AnalysisResponse; cross_exam_tracks: CrossExamTrack[]; total_tracks: number }> => {
    const response = await apiClient.post('/analyze_with_tracks', data);
    return response.data;
  },

  // Generate cross-exam tracks from analysis
  generateTracks: async (analysis: AnalysisResponse): Promise<CrossExamTracksResponse> => {
    const response = await apiClient.post<CrossExamTracksResponse>('/generate_tracks', analysis);
    return response.data;
  },
};

export default analysisApi;
