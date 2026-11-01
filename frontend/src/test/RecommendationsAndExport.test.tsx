import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { RecommendationsPage } from '../pages/RecommendationsPage'
import { ExportPage } from '../pages/ExportPage'
import { renderWithRoute } from './utils'
import * as analysesService from '../services/analyses'
import * as resumesService from '../services/resumes'

vi.mock('../services/analyses', () => ({
  getReport: vi.fn(),
  listRecommendations: vi.fn(),
  decideRecommendation: vi.fn(),
  regenerateRecommendation: vi.fn(),
  listExports: vi.fn(),
  createExport: vi.fn(),
}))

vi.mock('../services/resumes', () => ({
  listRevisions: vi.fn(),
}))

describe('Recommendations and Export Pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('RecommendationsPage', () => {
    it('renders recommendations list and allows accepting a proposal', async () => {
      vi.mocked(analysesService.getReport).mockResolvedValueOnce({
        id: 'ana_1',
        resume_id: 'res_1',
        created_at: new Date().toISOString(),
        scores: {
          methodology_version: '1.0.0',
          overall: 82.5,
          band: 'competent',
          components: {},
        },
        findings: [],
        ats: {} as any,
      } as any)

      vi.mocked(analysesService.listRecommendations).mockResolvedValueOnce([
        {
          id: 'rec_101',
          analysis_id: 'ana_1',
          category: 'experience_bullet',
          priority: 'high',
          state: 'pending',
          original_text: 'Worked on database queries.',
          proposed_text: 'Optimised 15+ PostgreSQL queries, reducing latency by 40%.',
          confidence: 'high',
          reason: 'Quantify impact with metrics.',
          source: 'gemini',
        } as any,
      ])

      vi.mocked(analysesService.decideRecommendation).mockResolvedValueOnce({
        id: 'rec_101',
        state: 'accepted',
      } as any)

      renderWithRoute(<RecommendationsPage />, {
        path: '/app/analyses/:analysisId/recommendations',
        entry: '/app/analyses/ana_1/recommendations',
      })

      await waitFor(() => {
        expect(screen.getByText(/Optimised 15\+ PostgreSQL queries/i)).toBeInTheDocument()
      })

      const acceptBtn = screen.getByRole('button', { name: /^accept$/i })
      fireEvent.click(acceptBtn)

      await waitFor(() => {
        expect(analysesService.decideRecommendation).toHaveBeenCalledWith('rec_101', 'accept', undefined)
      })
    })

    it('allows regenerating AI recommendation', async () => {
      vi.mocked(analysesService.getReport).mockResolvedValueOnce({
        id: 'ana_1',
        resume_id: 'res_1',
        created_at: new Date().toISOString(),
        scores: { methodology_version: '1.0.0', overall: 75.0, band: 'competent', components: {} },
        findings: [],
        ats: {} as any,
      } as any)

      vi.mocked(analysesService.listRecommendations).mockResolvedValueOnce([
        {
          id: 'rec_202',
          analysis_id: 'ana_1',
          category: 'summary',
          priority: 'medium',
          state: 'pending',
          original_text: 'Experienced coder.',
          proposed_text: 'Results-driven full stack engineer with 5 years experience.',
          confidence: 'medium',
          reason: 'Expand summary with professional context.',
          source: 'rules',
        } as any,
      ])

      vi.mocked(analysesService.regenerateRecommendation).mockResolvedValueOnce({
        id: 'rec_202',
        analysis_id: 'ana_1',
        category: 'summary',
        priority: 'medium',
        state: 'pending',
        original_text: 'Experienced coder.',
        proposed_text: 'Cloud-native backend architect specialising in distributed microservices.',
        confidence: 'high',
        reason: 'Expand summary with professional context.',
        source: 'gemini',
      } as any)

      renderWithRoute(<RecommendationsPage />, {
        path: '/app/analyses/:analysisId/recommendations',
        entry: '/app/analyses/ana_1/recommendations',
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /regenerate/i })).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /regenerate/i }))

      await waitFor(() => {
        expect(analysesService.regenerateRecommendation).toHaveBeenCalledWith('rec_202')
      })
    })
  })

  describe('ExportPage', () => {
    it('renders completed export with working download link', async () => {
      vi.mocked(analysesService.getReport).mockResolvedValueOnce({
        id: 'ana_1',
        resume_id: 'res_1',
        created_at: new Date().toISOString(),
      } as any)

      vi.mocked(resumesService.listRevisions).mockResolvedValueOnce([])

      vi.mocked(analysesService.listExports).mockResolvedValueOnce([
        {
          id: 'exp_1',
          analysis_id: 'ana_1',
          kind: 'analysis_report',
          format: 'pdf',
          status: 'completed',
          download_url: 'https://example.com/api/v1/exports/exp_1/download?token=xyz123',
          size_bytes: 45000,
          expires_at: new Date(Date.now() + 3600000).toISOString(),
          created_at: new Date().toISOString(),
        } as any,
      ])

      renderWithRoute(<ExportPage />, {
        path: '/app/analyses/:analysisId/export',
        entry: '/app/analyses/ana_1/export',
      })

      await waitFor(() => {
        const downloadLink = screen.getByRole('link', { name: /^Download$/i })
        expect(downloadLink).toBeInTheDocument()
        expect(downloadLink).toHaveAttribute('href', expect.stringContaining('token=xyz123'))
      })
    })

    it('triggers export generation on click', async () => {
      vi.mocked(analysesService.getReport).mockResolvedValueOnce({
        id: 'ana_1',
        resume_id: 'res_1',
        created_at: new Date().toISOString(),
      } as any)
      vi.mocked(resumesService.listRevisions).mockResolvedValueOnce([])
      vi.mocked(analysesService.listExports).mockResolvedValueOnce([])
      vi.mocked(analysesService.createExport).mockResolvedValueOnce({
        id: 'exp_new',
        status: 'pending',
      } as any)

      renderWithRoute(<ExportPage />, {
        path: '/app/analyses/:analysisId/export',
        entry: '/app/analyses/ana_1/export',
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Generate report PDF/i })).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Generate report PDF/i }))

      await waitFor(() => {
        expect(analysesService.createExport).toHaveBeenCalledWith({
          analysis_id: 'ana_1',
          kind: 'analysis_report',
          format: 'pdf',
          revision_id: null,
        })
      })
    })
  })
})
