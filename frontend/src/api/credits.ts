import apiClient from './client';

export interface CreditTransaction {
  id: string;
  type: string;
  amount: number;
  balance_after: number;
  description: string;
  created_at: string | null;
}

export interface UserCreditsInfo {
  balance: number;
  total_granted: number;
  total_consumed: number;
  last_transaction_at: string | null;
  recent_transactions: CreditTransaction[];
}

const creditsApi = {
  /** Get current user's credit balance and recent transactions */
  getMyCredits: async (): Promise<UserCreditsInfo> => {
    const response = await apiClient.get<UserCreditsInfo>('/api/v1/me/credits');
    return response.data;
  },
};

export default creditsApi;
