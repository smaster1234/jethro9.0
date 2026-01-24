// User & Auth Types
export interface User {
  id: string;
  email: string;
  name: string;
  firm_id: string;
  firm_name?: string;
  system_role: 'super_admin' | 'admin' | 'member' | 'viewer';
  professional_role?: string;
  is_admin: boolean;
  is_super_admin: boolean;
  teams?: TeamMembership[];
  team_leader_of?: string[];
}

export interface TeamMembership {
  team_id: string;
  team_name: string;
  team_role: 'team_leader' | 'team_member';
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  firm_id?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// Firm Types
export interface Firm {
  id: string;
  name: string;
  domain?: string;
  created_at: string;
}

// Team Types
export interface Team {
  id: string;
  firm_id: string;
  name: string;
  description?: string;
  created_at: string;
  members?: TeamMember[];
}

export interface TeamMember {
  id: string;
  user_id: string;
  name: string;
  email: string;
  team_role: 'team_leader' | 'team_member';
  added_at: string;
}

// Case Types
export interface Case {
  id: string;
  name: string;
  client_name: string;
  our_side: 'plaintiff' | 'defendant' | 'other';
  opponent_name?: string;
  court?: string;
  case_number?: string;
  description?: string;
  status?: 'active' | 'closed' | 'pending';
  tags?: string[];
  firm_id: string;
  document_count?: number;
  created_at: string;
  updated_at?: string;
}

export interface CreateCaseRequest {
  name: string;
  description?: string;
  client_name: string;
  our_side?: 'plaintiff' | 'defendant' | 'other';
  opponent_name?: string;
  court?: string;
  case_number?: string;
}

// Document Types
export interface Document {
  id: string;
  case_id: string;
  doc_name: string;
  original_filename?: string;
  mime_type?: string;
  party?: string;
  role?: string;
  author?: string;
  version_label?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  page_count?: number;
  language?: string;
  size_bytes?: number;
  text?: string;
  extracted_text?: string;
  text_hash?: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface DocumentUploadMetadata {
  name?: string;
  party?: string;
  role?: string;
  author?: string;
  version_label?: string;
}

export interface UploadResponse {
  document_ids: string[];
  job_ids: string[];
  message: string;
}

// Folder Types
export interface Folder {
  id: string;
  name: string;
  parent_id?: string;
  scope_type: string;
  created_at: string;
  children?: Folder[];
  document_count?: number;
}

// Job Types
export interface Job {
  job_id: string;
  status: 'queued' | 'started' | 'finished' | 'failed';
  progress?: number;
  result?: unknown;
  error?: string;
  started_at?: string;
  ended_at?: string;
}

// Analysis Types
export interface Claim {
  id: string;
  text: string;
  source_name?: string;
  source_doc_id?: string;
  page_no?: number;
  block_index?: number;
  speaker?: string;
  category?: string;
  confidence?: number;
  metadata?: Record<string, unknown>;
}

export interface Contradiction {
  id: string;
  claim_a_id: string;
  claim_b_id: string;
  claim_a?: Claim;
  claim_b?: Claim;
  contradiction_type: string;
  tier: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
  confidence: number;
  explanation?: string;
  explanation_he?: string;
  evidence?: string;
  verified?: boolean;
  verifier_confidence?: number;
  created_at?: string;
}

export interface CrossExamQuestion {
  id?: string;
  question: string;
  target_claim_id?: string;
  strategy?: string;
  purpose?: string;
  severity?: string;
  follow_up?: string;
  follow_ups?: string[];
}

// Backend returns this structure for cross-exam questions
export interface CrossExamQuestionsOutput {
  contradiction_id: string;
  target_party?: string;
  questions: CrossExamQuestion[];
  goal?: string;
}

export interface CrossExamTrack {
  id: string;
  name: string;
  description?: string;
  contradiction_id?: string;
  questions: CrossExamQuestion[];
  priority?: number;
}

export interface AnalysisResponse {
  claims: Claim[];
  claim_results?: Record<string, unknown>;
  contradictions: Contradiction[];
  // Backend returns array of CrossExamQuestionsOutput (grouped by contradiction)
  cross_exam_questions: CrossExamQuestionsOutput[] | CrossExamQuestion[];
  metadata?: {
    total_claims?: number;
    total_contradictions?: number;
    duration_ms?: number;
    validation_flags?: string[];
  };
}

export interface AnalysisRun {
  id: string;
  case_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  completed_at?: string;
  claims_count?: number;
  contradictions_count?: number;
  input_document_ids?: string[];
  metadata?: Record<string, unknown>;
  contradictions?: Contradiction[];
}

// Health Check
export interface HealthResponse {
  status: string;
  version?: string;
  llm_mode?: string;
  timestamp: string;
}

// API Error
export interface ApiError {
  detail: string;
  status?: number;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
