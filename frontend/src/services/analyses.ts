import { authedRequest } from './client'
import type {
  Analysis,
  AnalysisDetail,
  AnalysisList,
  ExportRecord,
  Job,
  Match,
  Recommendation,
} from '../types/domain'

/* ------------------------------------------------------------ analyses --- */

export function createAnalysis(resumeId: string, jobId?: string): Promise<AnalysisDetail> {
  return authedRequest<AnalysisDetail>('/api/v1/analyses', {
    method: 'POST',
    body: { resume_id: resumeId, job_id: jobId ?? null },
  })
}

export function listAnalyses(limit = 20): Promise<AnalysisList> {
  return authedRequest<AnalysisList>(`/api/v1/analyses?limit=${limit}`)
}

export function getAnalysis(analysisId: string): Promise<AnalysisDetail> {
  return authedRequest<AnalysisDetail>(`/api/v1/analyses/${analysisId}`)
}

export function getReport(analysisId: string): Promise<AnalysisDetail> {
  return authedRequest<AnalysisDetail>(`/api/v1/analyses/${analysisId}/report`)
}

export function deleteAnalysis(analysisId: string): Promise<void> {
  return authedRequest<void>(`/api/v1/analyses/${analysisId}`, { method: 'DELETE' })
}

/* ------------------------------------------------------- recommendations --- */

export function listRecommendations(analysisId: string): Promise<Recommendation[]> {
  return authedRequest<Recommendation[]>(`/api/v1/analyses/${analysisId}/recommendations`)
}

export function decideRecommendation(
  recommendationId: string,
  decision: 'accept' | 'reject' | 'edit',
  editedText?: string,
): Promise<Recommendation> {
  return authedRequest<Recommendation>(`/api/v1/recommendations/${recommendationId}/decision`, {
    method: 'POST',
    body: { decision, edited_text: editedText ?? null },
  })
}

/* ----------------------------------------------------------------- jobs --- */

export function createJob(input: {
  title?: string
  company?: string
  description: string
}): Promise<Job> {
  return authedRequest<Job>('/api/v1/jobs', { method: 'POST', body: input })
}

export function listJobs(): Promise<Job[]> {
  return authedRequest<Job[]>('/api/v1/jobs')
}

export function deleteJob(jobId: string): Promise<void> {
  return authedRequest<void>(`/api/v1/jobs/${jobId}`, { method: 'DELETE' })
}

export function createMatch(resumeId: string, jobId: string): Promise<Match> {
  return authedRequest<Match>('/api/v1/matches', {
    method: 'POST',
    body: { resume_id: resumeId, job_id: jobId },
  })
}

export function getMatch(matchId: string): Promise<Match> {
  return authedRequest<Match>(`/api/v1/matches/${matchId}`)
}

/* -------------------------------------------------------------- exports --- */

export function createExport(input: {
  analysis_id: string
  kind: 'analysis_report' | 'improved_resume'
  format: 'pdf' | 'docx'
  revision_id?: string | null
}): Promise<ExportRecord> {
  return authedRequest<ExportRecord>('/api/v1/exports', { method: 'POST', body: input })
}

export function getExport(exportId: string): Promise<ExportRecord> {
  return authedRequest<ExportRecord>(`/api/v1/exports/${exportId}`)
}

/** Every export generated for one analysis, newest first. */
export function listExports(analysisId: string): Promise<ExportRecord[]> {
  return authedRequest<ExportRecord[]>(`/api/v1/analyses/${analysisId}/exports`)
}

export function deleteExport(exportId: string): Promise<void> {
  return authedRequest<void>(`/api/v1/exports/${exportId}`, { method: 'DELETE' })
}

/** Analyse in one call: upload-free analyses list convenience for the dashboard. */
export type { Analysis, AnalysisDetail, AnalysisList }
