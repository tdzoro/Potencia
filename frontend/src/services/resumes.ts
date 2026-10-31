import { authedRequest, authedUpload } from './client'
import type {
  AnalysisDetail,
  CreateRevisionPayload,
  Resume,
  ResumeList,
  Revision,
} from '../types/domain'

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024
export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx']

export function uploadResume(file: File): Promise<Resume> {
  return authedUpload<Resume>('/api/v1/resumes', file)
}

export function listResumes(limit = 20): Promise<ResumeList> {
  return authedRequest<ResumeList>(`/api/v1/resumes?limit=${limit}`)
}

export function getResume(resumeId: string): Promise<Resume> {
  return authedRequest<Resume>(`/api/v1/resumes/${resumeId}`)
}

export function deleteResume(resumeId: string): Promise<void> {
  return authedRequest<void>(`/api/v1/resumes/${resumeId}`, { method: 'DELETE' })
}

export function listRevisions(resumeId: string): Promise<Revision[]> {
  return authedRequest<Revision[]>(`/api/v1/resumes/${resumeId}/revisions`)
}

export function createRevision(resumeId: string, payload: CreateRevisionPayload): Promise<Revision> {
  return authedRequest<Revision>(`/api/v1/resumes/${resumeId}/revisions`, {
    method: 'POST',
    body: payload,
  })
}

export function analyseResume(resumeId: string): Promise<AnalysisDetail> {
  return authedRequest<AnalysisDetail>('/api/v1/analyses', {
    method: 'POST',
    body: { resume_id: resumeId },
  })
}
