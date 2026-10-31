import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '../components/Badge'
import { ErrorNotice, PageHeader } from '../components/States'
import {
  ACCEPTED_EXTENSIONS,
  MAX_UPLOAD_BYTES,
  analyseResume,
  uploadResume,
} from '../services/resumes'
import type { Resume, SectionPresence } from '../types/domain'

const SECTION_LABELS: Array<[keyof SectionPresence, string]> = [
  ['contact', 'Contact'],
  ['summary', 'Summary'],
  ['experience', 'Experience'],
  ['education', 'Education'],
  ['skills', 'Skills'],
  ['projects', 'Projects'],
  ['certifications', 'Certifications'],
  ['achievements', 'Achievements'],
  ['leadership', 'Leadership'],
]

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function problemWith(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return 'Only PDF and DOCX documents are accepted.'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `That file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`
  }
  if (file.size === 0) {
    return 'That file is empty.'
  }
  return null
}

export function UploadPage() {
  const [file, setFile] = useState<File | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [resume, setResume] = useState<Resume | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const upload = useMutation({
    mutationFn: uploadResume,
    onSuccess: (data) => {
      setResume(data)
      void queryClient.invalidateQueries({ queryKey: ['resumes'] })
    },
  })

  const analyse = useMutation({
    mutationFn: analyseResume,
    onSuccess: (analysis) => {
      void queryClient.invalidateQueries({ queryKey: ['analyses'] })
      navigate(`/app/analyses/${analysis.id}`)
    },
  })

  function accept(candidate: File | null): void {
    setProblem(null)
    upload.reset()
    analyse.reset()
    setResume(null)

    if (!candidate) {
      setFile(null)
      return
    }

    const issue = problemWith(candidate)
    if (issue) {
      setFile(null)
      setProblem(issue)
      if (inputRef.current) {
        inputRef.current.value = ''
      }
      return
    }

    setFile(candidate)
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>): void {
    const selected = event.target.files?.[0] ?? null
    accept(selected)
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>): void {
    event.preventDefault()
    setDragging(false)
    accept(event.dataTransfer.files?.[0] ?? null)
  }

  const structure = resume?.structure ?? null
  const extraction = resume?.extraction ?? null
  const presentSections = structure
    ? SECTION_LABELS.filter(([key]) => structure.sections[key])
    : []
  const missingSections = structure
    ? SECTION_LABELS.filter(([key]) => !structure.sections[key])
    : []
  const poorlyExtracted = Boolean(
    extraction && (extraction.confidence < 0.6 || presentSections.length < 3),
  )

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="New analysis"
        title="Upload a resume"
        description="PDF or DOCX, up to 5 MB. The document is validated by its actual contents before anything is read, and nothing extracted is stored until the parse succeeds."
      />

      <section aria-labelledby="upload-heading" className="flex flex-col gap-4">
        <h2 id="upload-heading" className="text-lg font-semibold text-ink">
          Choose a document
        </h2>

        <label
          htmlFor="resume-file"
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={[
            'panel flex cursor-pointer flex-col items-center gap-2 border-dashed px-6 py-12 text-center transition-colors',
            dragging ? 'border-electric bg-electric/5' : 'hover:border-electric/50',
          ].join(' ')}
        >
          <span className="text-sm font-semibold text-ink">
            Drop a PDF or DOCX here, or click to browse
          </span>
          <span className="text-xs text-muted">
            {file ? `${file.name} · ${formatBytes(file.size)}` : 'The file is checked again on the server.'}
          </span>
          <input
            ref={inputRef}
            id="resume-file"
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(',')}
            onChange={handleChange}
            className="sr-only"
          />
        </label>

        {problem ? (
          <p className="text-sm text-rose-300" role="alert">
            {problem}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-primary"
            disabled={!file || upload.isPending}
            onClick={() => {
              if (file) {
                upload.mutate(file)
              }
            }}
          >
            {upload.isPending ? 'Reading the document…' : 'Upload and parse'}
          </button>
          {upload.isPending ? (
            <p className="text-xs text-muted">Extraction runs on the server; this usually takes a second.</p>
          ) : null}
        </div>

        {upload.isError ? (
          <ErrorNotice
            error={upload.error}
            title="That document could not be processed"
            onRetry={file ? () => upload.mutate(file) : undefined}
          />
        ) : null}
      </section>

      {resume ? (
        <section aria-labelledby="result-heading" className="flex flex-col gap-4">
          <h2 id="result-heading" className="text-lg font-semibold text-ink">
            What was read from the document
          </h2>

          {poorlyExtracted ? (
            <div className="panel border-amber-400/40 p-5">
              <p className="text-sm font-semibold text-amber-200">
                This document did not extract cleanly
              </p>
              <p className="mt-2 text-sm text-muted">
                {extraction
                  ? `Extraction confidence is ${(extraction.confidence * 100).toFixed(0)}% and ${
                      presentSections.length
                    } of ${SECTION_LABELS.length} sections were recognised.`
                  : 'No extraction details were returned.'}{' '}
                A score computed from a poor parse describes the parse, not your resume — fix the
                document (a real text layer, standard section headings) and upload it again.
              </p>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="panel p-5">
              <p className="label">Pages</p>
              <p className="mt-2 font-mono text-xl text-ink">{resume.page_count ?? '—'}</p>
            </div>
            <div className="panel p-5">
              <p className="label">Extraction</p>
              <p className="mt-2 font-mono text-xl text-ink">{extraction?.method ?? '—'}</p>
              <p className="mt-1 text-xs text-muted">
                {extraction?.ocr_used ? 'OCR fallback used' : 'Text layer read directly'}
              </p>
            </div>
            <div className="panel p-5">
              <p className="label">Confidence</p>
              <p className="mt-2 font-mono text-xl text-ink">
                {extraction ? `${(extraction.confidence * 100).toFixed(0)}%` : '—'}
              </p>
              <p className="mt-1 text-xs text-muted">{extraction?.text_chars ?? 0} characters read</p>
            </div>
            <div className="panel p-5">
              <p className="label">Structure</p>
              <p className="mt-2 font-mono text-xl text-ink">
                {structure ? structure.experience.length : 0} roles
              </p>
              <p className="mt-1 text-xs text-muted">
                {structure ? structure.bullet_count : 0} bullets ·{' '}
                {structure ? structure.skills.explicit.length : 0} skills ·{' '}
                {structure ? structure.word_count : 0} words
              </p>
            </div>
          </div>

          <div className="panel flex flex-col gap-4 p-5">
            <div>
              <p className="label">Sections recognised</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {presentSections.length > 0 ? (
                  presentSections.map(([key, label]) => (
                    <Badge key={key} tone="ok">
                      {label}
                    </Badge>
                  ))
                ) : (
                  <p className="text-sm text-muted">No standard section headings were found.</p>
                )}
              </div>
            </div>

            {missingSections.length > 0 ? (
              <div>
                <p className="label">Not found</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {missingSections.map(([key, label]) => (
                    <Badge key={key} tone="neutral">
                      {label}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {extraction && extraction.warnings.length > 0 ? (
              <div>
                <p className="label">Warnings from the parser</p>
                <ul className="mt-2 flex list-disc flex-col gap-1 pl-4 text-sm text-amber-200/90">
                  {extraction.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="btn-primary"
              disabled={analyse.isPending || poorlyExtracted}
              onClick={() => analyse.mutate(resume.id)}
            >
              {analyse.isPending ? 'Scoring…' : 'Run analysis'}
            </button>
            {poorlyExtracted ? (
              <p className="text-xs text-muted">
                Scoring is blocked until the document parses cleanly — a score from a broken parse
                would be a number about nothing.
              </p>
            ) : null}
          </div>

          {analyse.isError ? (
            <ErrorNotice
              error={analyse.error}
              title="The analysis could not be completed"
              onRetry={() => analyse.mutate(resume.id)}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
