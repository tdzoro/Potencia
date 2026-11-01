/**
 * Capture the product's real screens for the README.
 *
 * Requires a live stack: the API (`API_BASE_URL`) and a built web app served by
 * `npm run preview` (`WEB_URL`). It seeds its own account through the API, runs
 * the whole journey — upload, analysis, job match, an accepted recommendation, a
 * saved version, two exports — and then screenshots each screen. Nothing is
 * mocked, so the numbers inside the images are the numbers the engine produced.
 *
 *   API_BASE_URL=http://localhost:8010 WEB_URL=http://127.0.0.1:4173 \
 *     node scripts/capture_screenshots.mjs
 */

import { createRequire } from 'node:module'
import { readFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = require('playwright')

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = join(HERE, '..')
const OUT = join(ROOT, 'assets', 'readme')
const API = process.env.API_BASE_URL ?? 'http://localhost:8010'
const WEB = process.env.WEB_URL ?? 'http://127.0.0.1:4173'

const JOB = `Senior Backend Engineer
Requirements:
We need 5+ years of Python experience, PostgreSQL, Kubernetes and Terraform.
Nice to have: Kafka, GraphQL.
Responsibilities:
Own the payment ledger service and mentor engineers.
Bachelor's degree in Computer Science required.
`

async function json(path, { method = 'GET', token, body } = {}) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(`${method} ${path} -> ${response.status} ${JSON.stringify(payload)}`)
  }
  return payload
}

async function seed() {
  const email = `shots-${Date.now()}@example.com`
  const registered = await json('/api/v1/auth/register', {
    method: 'POST',
    body: { email, password: 'a-long-enough-password', display_name: 'Arjun Mehta' },
  })
  const token = registered.tokens.access_token

  const pdf = readFileSync(join(ROOT, 'frontend', 'e2e', 'fixtures', 'resume.pdf'))
  const form = new FormData()
  form.append('file', new Blob([pdf], { type: 'application/pdf' }), 'arjun-mehta.pdf')
  const uploaded = await fetch(`${API}/api/v1/resumes`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!uploaded.ok) {
    throw new Error(`upload failed: ${uploaded.status} ${await uploaded.text()}`)
  }
  const resume = await uploaded.json()

  const analysis = await json('/api/v1/analyses', {
    method: 'POST',
    token,
    body: { resume_id: resume.id },
  })

  const job = await json('/api/v1/jobs', {
    method: 'POST',
    token,
    body: { title: 'Senior Backend Engineer', description: JOB },
  })
  const match = await json('/api/v1/matches', {
    method: 'POST',
    token,
    body: { resume_id: resume.id, job_id: job.id },
  })

  const recommendations = await json(`/api/v1/analyses/${analysis.id}/recommendations`, { token })
  if (recommendations.length) {
    await json(`/api/v1/recommendations/${recommendations[0].id}/decision`, {
      method: 'POST',
      token,
      body: { decision: 'accept' },
    })
  }

  // A named revision, so the studio and export screens have real versions to show.
  await json(`/api/v1/resumes/${resume.id}/revisions`, {
    method: 'POST',
    token,
    body: {
      parent_id: null,
      label: 'Platform',
      content: {
        ...resume.structure,
        summary: {
          ...resume.structure.summary,
          text: 'Backend engineer focused on payment reliability and platform tooling.',
        },
      },
    },
  })

  await json('/api/v1/exports', {
    method: 'POST',
    token,
    body: { analysis_id: analysis.id, kind: 'analysis_report', format: 'pdf' },
  })
  await json('/api/v1/exports', {
    method: 'POST',
    token,
    body: { analysis_id: analysis.id, kind: 'improved_resume', format: 'pdf' },
  })

  return { token, resumeId: resume.id, analysisId: analysis.id, overall: analysis.scores.overall, match: match.result.estimate }
}

const SHOTS = [
  { name: 'ui-landing', path: '/', text: /resume/i, guest: true },
  { name: 'ui-dashboard', path: '/app', text: /score/i },
  { name: 'ui-report', path: (s) => `/app/analyses/${s.analysisId}`, text: /ATS compatibility/i },
  {
    name: 'ui-recommendations',
    path: (s) => `/app/analyses/${s.analysisId}/recommendations`,
    text: /recommendation/i,
  },
  {
    name: 'ui-match',
    path: (s) => `/app/analyses/${s.analysisId}/match`,
    text: /match estimate/i,
    // The panel starts empty: a match is produced by submitting a description.
    prepare: async (page) => {
      await page.getByRole('textbox', { name: 'Description' }).fill(JOB)
      await page.getByRole('button', { name: /match this job/i }).click()
    },
  },
  { name: 'ui-studio', path: (s) => `/app/resumes/${s.resumeId}/studio`, text: /revision/i },
  { name: 'ui-export', path: (s) => `/app/analyses/${s.analysisId}/export`, text: /download/i },
  { name: 'ui-history', path: '/app/history', text: /arjun/i },
]

async function main() {
  mkdirSync(OUT, { recursive: true })
  const seeded = await seed()
  console.log(`seeded: overall ${seeded.overall}, match ${seeded.match}`)

  const browser = await chromium.launch({ args: ['--no-sandbox'] })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    // 1x keeps each PNG a few hundred KB rather than several MB: the README
    // displays them around 900px wide, so nothing is lost by not doubling pixels.
    deviceScaleFactor: 1,
    colorScheme: 'light',
  })
  await context.addInitScript((token) => {
    window.localStorage.setItem('potencia.access_token', token)
    window.localStorage.setItem('potencia.refresh_token', 'screenshot-refresh-token')
  }, seeded.token)

  for (const shot of SHOTS) {
    const page = await context.newPage()
    const path = typeof shot.path === 'function' ? shot.path(seeded) : shot.path
    if (shot.guest) {
      await page.addInitScript(() => window.localStorage.clear())
    }
    await page.goto(WEB + path, { waitUntil: 'networkidle' })
    if (shot.prepare) {
      await shot.prepare(page)
    }
    await page.getByText(shot.text).first().waitFor({ state: 'visible', timeout: 20_000 })
    await page.waitForTimeout(700)
    const body = (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 70)
    console.log(`  ${shot.name}: ${body}`)
    await page.screenshot({ path: join(OUT, `${shot.name}.png`), fullPage: true })
    await page.close()
  }

  await browser.close()
  console.log(`wrote ${SHOTS.length} screenshots to assets/readme/`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
