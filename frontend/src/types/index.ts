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
  credits?: number;
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

// Organization Types (B1)
export interface Organization {
  id: string;
  firm_id: string;
  name: string;
  created_at?: string;
}

export interface OrganizationMember {
  user_id: string;
  email: string;
  name: string;
  role: 'viewer' | 'intern' | 'lawyer' | 'owner';
  added_at?: string;
}

export interface OrganizationInvite {
  id: string;
  organization_id: string;
  email: string;
  role: 'viewer' | 'intern' | 'lawyer' | 'owner';
  status: 'pending' | 'accepted' | 'expired' | 'revoked';
  expires_at: string;
  token?: string;
  created_at?: string;
}

export interface UserSearchResult {
  id: string;
  email: string;
  name: string;
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
  organization_id?: string;
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
  organization_id?: string;
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
  doc_class?: 'primary_pleading' | 'affidavit' | 'summation' | 'motion' | 'supporting';
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

// Witness Types
export interface WitnessVersion {
  id: string;
  witness_id: string;
  document_id: string;
  document_name?: string;
  version_type?: string;
  version_date?: string;
  created_at?: string;
  extra_data?: Record<string, unknown>;
}

export interface Witness {
  id: string;
  case_id: string;
  name: string;
  side?: string;
  created_at?: string;
  extra_data?: Record<string, unknown>;
  versions?: WitnessVersion[];
}

export interface VersionShift {
  shift_type: string;
  description: string;
  similarity?: number;
  details?: Record<string, unknown>;
  anchor_a?: EvidenceAnchor;
  anchor_b?: EvidenceAnchor;
}

export interface WitnessVersionDiffResponse {
  witness_id: string;
  version_a_id: string;
  version_b_id: string;
  similarity: number;
  shifts: VersionShift[];
}

export interface ContradictionInsight {
  contradiction_id: string;
  impact_score: number;
  risk_score: number;
  verifiability_score: number;
  stage_recommendation?: 'early' | 'mid' | 'late' | string;
  prerequisites?: string[];
  expected_evasions?: string[];
  best_counter_questions?: string[];
  do_not_ask_flag?: boolean;
  do_not_ask_reason?: string | null;
  composite_score?: number;
}

export interface CrossExamPlanBranch {
  trigger: string;
  follow_up_questions: string[];
}

export interface CrossExamPlanStep {
  id: string;
  contradiction_id?: string;
  stage: string;
  step_type: string;
  title: string;
  question: string;
  purpose?: string;
  anchors?: EvidenceAnchor[];
  branches?: CrossExamPlanBranch[];
  do_not_ask_flag?: boolean;
  do_not_ask_reason?: string | null;
}

export interface CrossExamPlanStage {
  stage: string;
  steps: CrossExamPlanStep[];
}

export interface CrossExamPlanResponse {
  plan_id: string;
  case_id: string;
  run_id: string;
  witness_id?: string;
  created_at?: string;
  stages: CrossExamPlanStage[];
}

export interface WitnessSimulationStep {
  step_id: string;
  stage: string;
  question: string;
  witness_reply: string;
  chosen_branch_trigger?: string | null;
  follow_up_questions?: string[];
  warnings?: string[];
}

export interface WitnessSimulationResponse {
  run_id: string;
  plan_id: string;
  persona: string;
  steps: WitnessSimulationStep[];
}

// Training Types (C1)
export interface TrainingSession {
  session_id: string;
  case_id: string;
  plan_id: string;
  witness_id?: string | null;
  persona?: string | null;
  status: 'active' | 'finished' | 'cancelled';
  back_remaining: number;
  created_at?: string;
}

export interface TrainingTurn {
  turn_id: string;
  session_id: string;
  step_id: string;
  stage?: string | null;
  question: string;
  witness_reply?: string | null;
  chosen_branch?: string | null;
  follow_up_questions?: string[];
  warnings?: string[];
}

export interface TrainingSummary {
  total_turns: number;
  stages: Record<string, number>;
  branches: Record<string, number>;
  warnings: number;
}

export interface EntityUsageSummary {
  entity_type: string;
  entity_id: string;
  usage: Record<string, string>;
  latest_used_at?: string | null;
}

export interface FeedbackItem {
  id: string;
  org_id?: string | null;
  case_id: string;
  entity_type: 'insight' | 'plan_step';
  entity_id: string;
  label: 'worked' | 'not_worked' | 'too_risky' | 'excellent';
  note?: string | null;
  created_at?: string;
  created_by: string;
}

export interface FeedbackAggregate {
  entity_type: 'insight' | 'plan_step';
  entity_id: string;
  counts: Record<string, number>;
  latest_at?: string;
}

export interface FeedbackListResponse {
  items: FeedbackItem[];
  aggregates: FeedbackAggregate[];
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
  message?: string;
  result?: unknown;
  error?: string;
  started_at?: string;
  ended_at?: string;
  structured_progress?: StructuredProgress;
}

export interface StructuredProgress {
  overall_pct: number;
  current_stage: string | null;
  current_stage_label: string;
  elapsed_sec: number;
  stages: ProgressStage[];
  preview: ProgressPreview;
  error: string | null;
  job_status?: string;
  final?: boolean;
}

export interface ProgressStage {
  key: string;
  label_he: string;
  started_at: number;
  finished_at: number;
  progress_pct: number;
  detail: string;
  counts: Record<string, number>;
  elapsed_sec?: number;
}

export interface ProgressPreview {
  documents_total: number;
  documents_processed: number;
  claims_extracted: number;
  contradictions_found: number;
  contradictions_verified: number;
  contradictions_rejected: number;
  first_contradictions: PreviewContradiction[];
}

export interface PreviewContradiction {
  claim_a: string;
  claim_b: string;
  type: string;
  severity: string;
  confidence: number;
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
  // V2 enrichment fields
  speaker_role?: string;
  speaker_mode?: string;   // finding | party_claim | quote | law_citation
  plane?: string;          // FACT | LAW | OPINION | PROCEDURAL
  time_reference?: string;
  modality?: string;       // certain | possible | obligation | permission
  scope_quantifiers?: string;
  entities?: string[];
  negation?: boolean;
  context_before?: string;
  context_after?: string;
  section_path?: string;
}

export interface EvidenceAnchor {
  doc_id: string;
  page_no?: number;
  block_index?: number;
  paragraph_index?: number;
  char_start?: number;
  char_end?: number;
  snippet?: string;
  bbox?: { x: number; y: number; width: number; height: number };
}

export interface AnchorResolveResponse {
  doc_id: string;
  doc_name: string;
  page_no?: number;
  block_index?: number;
  paragraph_index?: number;
  char_start?: number;
  char_end?: number;
  text: string;
  context_before?: string;
  context_after?: string;
  highlight_start?: number;
  highlight_end?: number;
  highlight_text?: string;
  bbox?: Record<string, unknown>;
}

export interface ClaimEvidence {
  claim_id: string;
  doc_id?: string;
  locator?: Record<string, unknown>;
  anchor?: EvidenceAnchor;
  quote: string;
  normalized?: string;
  // Enrichment fields (Cursor 5.2 §10 — Expert Notebook)
  speaker_mode?: string;   // finding | party_claim | quote | law_citation | opinion
  speaker_role?: string;
  plane?: string;          // FACT | LAW | OPINION | PROCEDURAL
  modality?: string;       // certain | possible | obligation | permission
  negation?: boolean;
  entities?: string[];
  context_before?: string;
  context_after?: string;
}

export interface GateResults {
  claim_a_complete?: boolean;
  claim_b_complete?: boolean;
  time_match?: boolean;
  scope_match?: boolean;
  quantifier_match?: boolean;
  modality_match?: boolean;
  speaker_mode_ok?: boolean;
  plane_match?: boolean;
  [key: string]: unknown;
}

export interface Contradiction {
  id: string;
  // Claim IDs (backend uses both naming conventions)
  claim_a_id?: string;
  claim_b_id?: string;
  claim1_id?: string;
  claim2_id?: string;
  // Claim objects
  claim_a?: Claim;
  claim_b?: Claim;
  // Enriched claim evidence (from API response)
  claim1?: ClaimEvidence;
  claim2?: ClaimEvidence;
  // Claim text (from enriched responses)
  claim1_text?: string;
  claim2_text?: string;
  // Type info
  contradiction_type?: string;
  type?: string;
  tier?: number;
  // Severity and status
  severity?: 'low' | 'medium' | 'high' | 'critical';
  status?: 'verified' | 'likely' | 'suspicious' | 'rejected' | 'new' | 'reviewed' | 'confirmed' | 'dismissed';
  bucket?: string;
  // Scores
  confidence?: number;
  verifier_confidence?: number;
  verified?: boolean;
  // Content
  explanation?: string;
  explanation_he?: string;
  evidence?: string;
  quote1?: string;
  quote2?: string;
  category?: string;
  // Locators
  claim1_locator?: EvidenceAnchor | Record<string, unknown>;
  claim2_locator?: EvidenceAnchor | Record<string, unknown>;
  // Timestamps
  created_at?: string;
  // Reconciliation details (Cursor 5.2 §10 — Expert Notebook)
  reconciler_outcome?: string;
  reconciler_rationale?: string;
  reconciliation_attempt?: string;
  deciding_fields?: string[];
  gate_results?: GateResults;
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

// Expert Notebook types (Cursor 5.2 §10)
export interface ExpertEvidence {
  quote: string;
  context_before?: string;
  context_after?: string;
  doc_id?: string;
  section_path?: string;
  locator?: Record<string, unknown>;
  speaker_mode?: string;
  speaker_role?: string;
  plane?: string;
  modality?: string;
  negation?: boolean;
  entities?: string[];
  time_reference?: string;
}

export interface PairGateResults {
  context_present?: boolean;
  speaker_mode_ok?: boolean;
  plane_match?: boolean;
  time_match?: boolean;
  scope_match?: boolean;
  reconciliation_failed?: boolean;
  [key: string]: unknown;
}

export interface PairAnalysisRow {
  pair_id: string;
  claim_a: ExpertEvidence;
  claim_b: ExpertEvidence;
  outcome_category: string;
  contradiction_score: number;
  severity: string;
  gates: PairGateResults;
  reconciliation_attempt?: string;
  rationale?: string;
  deciding_fields: string[];
  is_true_contradiction: boolean;
  blocked_reasons: string[];
}

export interface ExpertSummaryReport {
  total_pairs_analyzed: number;
  distribution: Record<string, number>;
  true_contradiction_count: number;
  noise_to_signal_ratio: number;
  top_findings: string[];
  validation_flags: string[];
}

export interface ExpertNotebookPayload {
  pair_analysis: PairAnalysisRow[];
  summary_report: ExpertSummaryReport;
}

export interface AnalysisResponse {
  claims: Claim[];
  claim_results?: Record<string, unknown>;
  contradictions: Contradiction[];
  // Backend returns array of CrossExamQuestionsOutput (grouped by contradiction)
  cross_exam_questions: CrossExamQuestionsOutput[] | CrossExamQuestion[];
  // Expert Notebook payload (Cursor 5.2 §10)
  expert_notebook?: ExpertNotebookPayload;
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
  contradictions_total?: number;
  contradictions_limit?: number;
  contradictions_offset?: number;
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
export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiError {
  error?: ApiErrorDetail;
  detail?: string;
  message?: string;
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
