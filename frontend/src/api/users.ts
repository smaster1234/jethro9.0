import apiClient from './client';

export interface UserLookupResult {
  id: string;
  email: string;
  name: string;
  system_role: string;
  firm_id: string;
  professional_role?: string;
}

export const usersApi = {
  // Lookup user by email
  lookupByEmail: async (email: string): Promise<UserLookupResult> => {
    const response = await apiClient.get<UserLookupResult>('/users/by-email', {
      params: { email },
    });
    return response.data;
  },
};

export default usersApi;
