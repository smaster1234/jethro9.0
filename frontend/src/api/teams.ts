import apiClient from './client';
import type { Team, TeamMember } from '../types';

export interface CreateTeamRequest {
  name: string;
  description?: string;
}

export interface AddMemberRequest {
  user_id: string;
  team_role: 'team_leader' | 'team_member';
}

export interface TeamWithMembers extends Team {
  members: TeamMember[];
}

export const teamsApi = {
  // List all teams in the current firm
  list: async (): Promise<Team[]> => {
    const response = await apiClient.get<Team[]>('/teams');
    return response.data;
  },

  // Get a specific team with members
  get: async (teamId: string): Promise<TeamWithMembers> => {
    const response = await apiClient.get<TeamWithMembers>(`/teams/${teamId}`);
    return response.data;
  },

  // Create a new team
  create: async (data: CreateTeamRequest): Promise<Team> => {
    const response = await apiClient.post<Team>('/teams', data);
    return response.data;
  },

  // Add a member to a team
  addMember: async (teamId: string, data: AddMemberRequest): Promise<void> => {
    await apiClient.post(`/teams/${teamId}/members`, data);
  },

  // Remove a member from a team
  removeMember: async (teamId: string, userId: string): Promise<void> => {
    await apiClient.delete(`/teams/${teamId}/members/${userId}`);
  },

  // Assign a team to a case
  assignToCase: async (caseId: string, teamId: string): Promise<void> => {
    await apiClient.post(`/cases/${caseId}/teams`, null, {
      params: { team_id: teamId },
    });
  },

  // Get teams assigned to a case
  getCaseTeams: async (caseId: string): Promise<Team[]> => {
    const response = await apiClient.get<Team[]>(`/cases/${caseId}/teams`);
    return response.data;
  },
};

export default teamsApi;
