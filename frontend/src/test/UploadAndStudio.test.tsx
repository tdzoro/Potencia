import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { UploadPage } from '../pages/UploadPage'
import { StudioPage } from '../pages/StudioPage'
import { renderWithProviders, renderWithRoute } from './utils'
import * as resumeService from '../services/resumes'

vi.mock('../services/resumes', async (importOriginal) => {
  const actual = await importOriginal<typeof resumeService>()
  return {
    ...actual,
    uploadResume: vi.fn(),
    analyseResume: vi.fn(),
    listRevisions: vi.fn(),
    createRevision: vi.fn(),
    compareRevisions: vi.fn(),
  }
})

describe('Upload and Studio Pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('UploadPage', () => {
    it('renders the upload dropzone and automatic OCR badge', () => {
      renderWithProviders(<UploadPage />)
      expect(screen.getByRole('heading', { name: /Upload a resume/i })).toBeInTheDocument()
      expect(screen.getAllByText(/Automatic OCR Enabled/i).length).toBeGreaterThan(0)
      expect(screen.getByText(/Drop a PDF or DOCX here/i)).toBeInTheDocument()
    })

    it('rejects unsupported file formats before uploading', () => {
      const { container } = renderWithProviders(<UploadPage />)
      const fileInput = container.querySelector('#resume-file') as HTMLInputElement

      const badFile = new File(['plain text content'], 'unsupported.txt', { type: 'text/plain' })
      fireEvent.change(fileInput, { target: { files: [badFile] } })

      expect(screen.getByText(/Only PDF and DOCX documents are accepted/i)).toBeInTheDocument()
      expect(resumeService.uploadResume).not.toHaveBeenCalled()
    })

    it('accepts valid PDF file and triggers upload mutation', async () => {
      vi.mocked(resumeService.uploadResume).mockResolvedValueOnce({
        id: 'res_123',
        status: 'parsed',
        filename: 'resume.pdf',
        mime_type: 'application/pdf',
        size_bytes: 1024,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        extraction: {
          text: 'Jane Doe Software Engineer',
          page_count: 1,
          method: 'ocr',
          confidence: 0.92,
          ocr_used: true,
          warnings: [],
        },
        structure: {
          contact: { name: 'Jane Doe', email: 'jane@example.com' },
          summary: { present: true, text: 'Senior developer' },
          experience: [],
          education: [],
          skills: { explicit: ['Python', 'PostgreSQL'] },
          sections: {
            contact: true,
            summary: true,
            experience: true,
            education: true,
            skills: true,
            projects: false,
            certifications: false,
            achievements: false,
            leadership: false,
          },
          word_count: 150,
          bullet_count: 4,
          page_count: 1,
          has_dates: true,
          date_formats: ['2023-01'],
          reading_order_risk: 'none',
        },
      } as any)

      const { container } = renderWithProviders(<UploadPage />)
      const fileInput = container.querySelector('#resume-file') as HTMLInputElement

      const goodFile = new File(['dummy-pdf'], 'valid_resume.pdf', { type: 'application/pdf' })
      fireEvent.change(fileInput, { target: { files: [goodFile] } })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Upload and parse/i })).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Upload and parse/i }))

      await waitFor(() => {
        expect(resumeService.uploadResume).toHaveBeenCalledWith(goodFile, expect.anything())
      })
    })
  })

  describe('StudioPage', () => {
    it('renders empty state when no revisions are found', async () => {
      vi.mocked(resumeService.listRevisions).mockResolvedValueOnce([])
      renderWithRoute(<StudioPage />, {
        path: '/app/resumes/:resumeId/studio',
        entry: '/app/resumes/res_empty/studio',
      })

      await waitFor(() => {
        expect(screen.getByText(/This resume has no revisions/i)).toBeInTheDocument()
      })
    })

    it('renders editor with loaded revision content', async () => {
      vi.mocked(resumeService.listRevisions).mockResolvedValueOnce([
        {
          id: 'rev_1',
          resume_id: 'res_123',
          revision_number: 0,
          label: 'Original Upload',
          content: {
            contact: { name: 'Jane Doe', email: 'jane@example.com' },
            summary: { present: true, text: 'Platform engineer with Kubernetes experience.' },
            experience: [],
            education: [],
            projects: [],
            skills: { explicit: ['Python', 'Docker'], inferred: [] },
            sections: { contact: true, summary: true, experience: false, education: false, skills: true },
            word_count: 100,
            bullet_count: 2,
            page_count: 1,
            has_dates: false,
            date_formats: [],
            reading_order_risk: 'none',
          },
          created_at: new Date().toISOString(),
        } as any,
      ])

      renderWithRoute(<StudioPage />, {
        path: '/app/resumes/:resumeId/studio',
        entry: '/app/resumes/res_123/studio',
      })

      await waitFor(() => {
        expect(screen.getByDisplayValue(/Platform engineer with Kubernetes experience/i)).toBeInTheDocument()
      })
    })
  })
})
