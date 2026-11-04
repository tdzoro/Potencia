/**
 * The API's data model, mirrored on the client.
 *
 * These types follow `docs/API.md` exactly. Where the API distinguishes two
 * states, the client does too — a `partial` skill match and an `absent` one are
 * different facts, and flattening them in the UI would misrepresent the report.
 */

export type Confidence = 'low' | 'medium' | 'high'
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type ScoreBand = 'critical' | 'developing' | 'competent' | 'strong' | 'exceptional'

export type ScoreCategory =
  | 'content_quality'
  | 'experience'
  | 'skills'
  | 'structure'
  | 'ats_compatibility'
  | 'language_readability'

export const SCORE_CATEGORY_LABELS: Record<ScoreCategory, string> = {
  content_quality: 'Content quality',
  experience: 'Experience & achievements',
  skills: 'Skills presentation',
  structure: 'Structure & organisation',
  ats_compatibility: 'ATS compatibility',
  language_readability: 'Language & readability',
}

/* ----------------------------------------------------------------- auth --- */

export interface User {
  id: string
  email: string
  display_name: string | null
  created_at: string
  email_verified: boolean
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface AuthResponse {
  user: User
  tokens: TokenPair
}

/* -------------------------------------------------------------- resumes --- */

export interface Bullet {
  text: string
  span: [number, number] | null
}

export interface Contact {
  name: string | null
  email: string | null
  phone: string | null
  links: string[]
}

export interface SummaryBlock {
  text: string | null
  present: boolean
}

export interface ExperienceEntry {
  title: string | null
  organisation: string | null
  start: string | null
  end: string | null
  date_precision: 'day' | 'month' | 'year' | 'present' | 'unknown'
  bullets: Bullet[]
}

export interface EducationEntry {
  institution: string | null
  degree: string | null
  field: string | null
  start: string | null
  end: string | null
  details: string[]
}

export interface ProjectEntry {
  name: string | null
  description: string | null
  technologies: string[]
  bullets: Bullet[]
}

export interface CertificationEntry {
  name: string
  issuer: string | null
  date: string | null
}

export interface InferredSkill {
  name: string
  basis: string
}

export interface SkillSet {
  explicit: string[]
  inferred: InferredSkill[]
}

export interface Uncertainty {
  field: string
  reason: string
}

export interface SectionPresence {
  contact: boolean
  summary: boolean
  experience: boolean
  education: boolean
  skills: boolean
  projects: boolean
  certifications: boolean
  achievements: boolean
  leadership: boolean
}

export interface ResumeStructure {
  contact: Contact
  summary: SummaryBlock
  experience: ExperienceEntry[]
  education: EducationEntry[]
  projects: ProjectEntry[]
  certifications: CertificationEntry[]
  achievements: string[]
  leadership: string[]
  skills: SkillSet
  sections: SectionPresence
  uncertain: Uncertainty[]
  word_count: number
  bullet_count: number
  page_count: number
  has_dates: boolean
  date_formats: string[]
  reading_order_risk: 'none' | 'low' | 'medium' | 'high'
}

export interface Extraction {
  confidence: number
  method: 'text_layer' | 'ocr' | 'partial' | 'failed' | string
  ocr_used: boolean
  text_chars: number
  warnings: string[]
}

export interface Resume {
  id: string
  original_filename: string
  media_type: string
  size_bytes: number
  page_count: number | null
  status: string
  created_at: string
  extraction: Extraction | null
  structure: ResumeStructure | null
  failure: Record<string, unknown> | null
}

export interface ResumeSummary {
  id: string
  original_filename: string
  page_count: number | null
  status: string
  created_at: string
  extraction: Extraction | null
}

export interface ResumeList {
  items: ResumeSummary[]
  next_cursor: string | null
  has_more: boolean
}

export interface Revision {
  id: string
  resume_id: string
  parent_id: string | null
  label: string | null
  applied_recommendations: string[]
  content: ResumeStructure | null
  created_at: string
}

export interface CreateRevisionPayload {
  content: ResumeStructure
  parent_id?: string | null
  label?: string | null
  applied_recommendation_ids?: string[]
}

export interface RevisionChange {
  field: string
  before: string | null
  after: string | null
}

export interface RevisionCompare {
  resume_id: string
  from_revision: string
  to_revision: string
  from_label: string | null
  to_label: string | null
  changes: RevisionChange[]
}

/* ------------------------------------------------------------ analyses --- */

export interface Evidence {
  section: string
  text: string
  page: number | null
}

export interface Finding {
  id: string
  category: ScoreCategory
  criterion: string
  severity: Severity
  title: string
  evidence: Evidence[]
  explanation: string
  remediation: string
  score_impact: number | null
  source: 'rules' | 'nlp' | 'llm'
}

export interface ScoreComponent {
  value: number
  weight: number
  confidence: Confidence
}

export interface ScoreBundle {
  methodology_version: string
  overall: number
  applicable_weight: number
  components: Record<ScoreCategory, ScoreComponent>
  job_match: number | null
  band: ScoreBand
}

export interface ATSCheck {
  id: string
  label: string
  status: 'pass' | 'warn' | 'fail'
  severity: Severity
  evidence: Evidence[]
  explanation: string
  remediation: string
}

export interface ATSReport {
  estimate: number
  disclaimer: string
  checks: ATSCheck[]
  summary: Record<string, number>
}

export interface Strength {
  text: string
  evidence: Evidence[]
}

export interface Analysis {
  id: string
  resume_id: string
  job_id: string | null
  status: 'queued' | 'running' | 'completed' | 'failed'
  methodology_version: string
  created_at: string
  completed_at: string | null
  failure: Record<string, unknown> | null
}

export interface AnalysisDetail extends Analysis {
  scores: ScoreBundle | null
  ats: ATSReport | null
  findings: Finding[]
  strengths: Strength[]
  priority_actions: string[]
}

export interface AnalysisList {
  items: Analysis[]
  next_cursor: string | null
  has_more: boolean
}

/* -------------------------------------------------------- recommend. ----- */

export type RecommendationCategory =
  | 'summary'
  | 'experience_bullet'
  | 'project_description'
  | 'achievement'
  | 'skills_organisation'
  | 'grammar'
  | 'clarity'
  | 'relevance'
  | 'keyword_placement'
  | 'formatting'

export interface UserInputPrompt {
  field: string
  question: string
}

export interface Recommendation {
  id: string
  analysis_id: string
  category: RecommendationCategory
  priority: 'high' | 'medium' | 'low'
  finding_id: string | null
  original_text: string | null
  proposed_text: string | null
  reason: string
  remediation: string
  requires_user_input: UserInputPrompt[]
  confidence: Confidence
  state: 'pending' | 'accepted' | 'rejected' | 'edited'
  source?: 'rules' | 'gemini' | string
  decided_at: string | null
}

/* --------------------------------------------------------------- jobs ---- */

export interface JobRequirements {
  required_skills: string[]
  preferred_skills: string[]
  min_years: number | null
  degree_level: string | null
  responsibilities: string[]
}

export interface Job {
  id: string
  title: string | null
  company: string | null
  created_at: string
  requirements: JobRequirements | null
}

export interface SkillMatch {
  name: string
  status: 'matched' | 'partial' | 'weakly_demonstrated' | 'absent'
  evidence: string[]
  note: string
}

export interface YearsRequirement {
  required: number | null
  demonstrated: number | null
  status: 'matched' | 'partial' | 'absent' | 'not_applicable'
}

export interface EducationRequirement {
  required: string | null
  status: 'matched' | 'partial' | 'absent' | 'not_applicable'
}

export interface ResponsibilityMatch {
  text: string
  status: 'matched' | 'partial' | 'absent' | 'not_applicable'
}

export interface Gap {
  name: string
  advice: string
}

export interface JobMatchResult {
  methodology_version: string
  estimate: number
  requirements: {
    required_skills: SkillMatch[]
    preferred_skills: SkillMatch[]
    experience_years: YearsRequirement
    education: EducationRequirement
    responsibilities: ResponsibilityMatch[]
  }
  gaps: Gap[]
  summary: Record<string, number>
}

export interface Match {
  id: string
  resume_id: string
  job_id: string
  status: string
  methodology_version: string
  created_at: string
  completed_at: string | null
  result: JobMatchResult | null
  failure: Record<string, unknown> | null
}

/* ------------------------------------------------------------- exports --- */

export interface ExportRecord {
  id: string
  analysis_id: string
  revision_id: string | null
  kind: 'analysis_report' | 'improved_resume'
  format: 'pdf' | 'docx'
  status: string
  size_bytes: number | null
  download_url: string | null
  expires_at: string | null
  failure: Record<string, unknown> | null
}
