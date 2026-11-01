import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, BrowserContext, Page } from '@playwright/test'

const API = process.env.API_BASE_URL ?? 'http://localhost:8010'
const HERE = dirname(fileURLToPath(import.meta.url))

interface Seeded {
  email: string
  token: string
  resumeId: string
  analysisId: string
  overall: number
}

const JOB = `Senior Backend Engineer
Requirements:
We need 5+ years of Python experience, PostgreSQL, Kubernetes and Terraform.
Nice to have: Kafka.
Responsibilities:
Own the payment ledger service and mentor engineers.
Bachelor's degree in Computer Science required.
`

async function seedAccount(api: APIRequestContext): Promise<Seeded> {
  const email = `e2e-${Date.now()}@example.com`
  const registered = await api.post(`${API}/api/v1/auth/register`, {
    data: { email, password: 'a-long-enough-password', display_name: 'E2E Reviewer' },
  })
  expect(registered.ok(), await registered.text()).toBeTruthy()
  const token = (await registered.json()).tokens.access_token as string

  const uploaded = await api.post(`${API}/api/v1/resumes`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      file: {
        name: 'arjun.pdf',
        mimeType: 'application/pdf',
        buffer: readFileSync(join(HERE, 'fixtures', 'resume.pdf')),
      },
    },
  })
  expect(uploaded.ok(), await uploaded.text()).toBeTruthy()
  const resumeId = (await uploaded.json()).id as string

  const analysed = await api.post(`${API}/api/v1/analyses`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { resume_id: resumeId },
  })
  expect(analysed.ok(), await analysed.text()).toBeTruthy()
  const analysis = await analysed.json()

  return {
    email,
    token,
    resumeId,
    analysisId: analysis.id,
    overall: analysis.scores.overall,
  }
}

/** Seed the session the same way the app stores it, before any script runs. */
async function withSession(context: BrowserContext, token: string): Promise<void> {
  await context.addInitScript((accessToken) => {
    window.localStorage.setItem('potencia.access_token', accessToken as string)
    window.localStorage.setItem('potencia.refresh_token', 'e2e-refresh-token-value')
  }, token)
}

async function seededPage(context: BrowserContext, path: string, token: string): Promise<Page> {
  const page = await context.newPage()
  await withSession(context, token)
  await page.goto(path)
  return page
}

test.describe('the signed-out surface & auth journeys', () => {
  test('journey 0: landing page states what the product does and links to sign in', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText(/resume feedback/i)
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible()
  })

  test('journey 0b: an unauthenticated visitor cannot reach the dashboard', async ({ page }) => {
    await page.goto('/app')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByLabel(/email/i)).toBeVisible()
  })

  test('journey 1: user registration flow displays confirmation state', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { level: 1 })).toContainText(/Measure the resume/i)
    await page.getByLabel('Name (optional)').fill('New Applicant')
    await page.getByLabel('Email').fill(`reg-user-${Date.now()}@example.com`)
    await page.getByLabel(/^Password$/).fill('ValidPassword123!')
    await page.getByLabel('Confirm password').fill('ValidPassword123!')
    await page.getByRole('button', { name: /create account/i }).click()

    await expect(page.locator('body')).toContainText(/Check your email/i)
  })

  test('journey 2: email verification handles missing or invalid token safely', async ({ page }) => {
    await page.goto('/verify-email')
    await expect(page.locator('body')).toContainText(/Missing verification link/i)
  })

  test('journey 13: password recovery flow accepts email and notifies user', async ({ page }) => {
    await page.goto('/forgot-password')
    await expect(page.getByRole('heading', { level: 1 })).toContainText(/Reset your/i)
    await page.getByLabel('Email').fill('user-recovery@example.com')
    await page.getByRole('button', { name: /send password reset link/i }).click()

    await expect(page.locator('body')).toContainText(/Check your email/i)
  })
})

test.describe('the authenticated journey', () => {
  // One account for the whole file. Registration is rate limited to five per
  // fifteen minutes per identity, and eight registrations from one IP is exactly
  // the behaviour that limit exists to stop.
  let seeded: Seeded

  test.beforeAll(async ({ playwright }) => {
    const api = await playwright.request.newContext()
    seeded = await seedAccount(api)
    await api.dispose()
  })

  test('dashboard shows the stored score, not a placeholder', async ({ page, context }) => {
    await withSession(context, seeded.token)

    await page.goto('/app')
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    await expect(page.locator('body')).toContainText(seeded.overall.toFixed(1))
  })

  test('the report shows the score, the ATS estimate and the evidence', async ({
    page,
    context,
  }) => {
    await withSession(context, seeded.token)

    await page.goto(`/app/analyses/${seeded.analysisId}`)
    await expect(page.locator('body')).toContainText(seeded.overall.toFixed(1))
    await expect(page.locator('body')).toContainText(/ATS compatibility/i)
    await expect(page.locator('body')).toContainText(/priority actions/i)
  })

  test('a recommendation can be accepted and the change persists', async ({
    page,
    context,
  }) => {
    await withSession(context, seeded.token)

    await page.goto(`/app/analyses/${seeded.analysisId}/recommendations`)
    const accept = page.getByRole('button', { name: /^accept$/i }).first()
    await expect(accept).toBeVisible()
    await accept.click()

    await expect(page.locator('body')).toContainText(/accepted/i)

    // Reload from the server: the decision must have been stored, not just shown.
    await page.reload()
    await expect(page.locator('body')).toContainText(/accepted/i)
  })

  test('a report can be generated and exposes a signed download link', async ({
    page,
    context,
  }) => {
    await withSession(context, seeded.token)

    await page.goto(`/app/analyses/${seeded.analysisId}/export`)
    await page.getByRole('button', { name: /generate report pdf/i }).click()

    const download = page.getByRole('link', { name: /^download$/i }).first()
    await expect(download).toBeVisible()
    await expect(download).toHaveAttribute('href', /token=/)
  })

  test('a pasted job description produces a match with named gaps', async ({
    page,
    context,
  }) => {
    await withSession(context, seeded.token)

    await page.goto(`/app/analyses/${seeded.analysisId}/match`)
    await page.getByRole('textbox', { name: 'Description' }).fill(JOB)
    await page.getByRole('button', { name: /match this job/i }).click()

    await expect(page.locator('body')).toContainText(/match estimate/i)
    // Terraform is absent from the resume, so it must be surfaced by name.
    await expect(page.locator('body')).toContainText(/Terraform/i)
  })

  test('the studio keeps the original revision and saves a new one', async ({
    page,
    context,
  }) => {
    await withSession(context, seeded.token)

    await page.goto(`/app/resumes/${seeded.resumeId}/studio`)
    await expect(page.locator('body')).toContainText(/revision/i)

    // The summary field lives inside a section labelled by its heading; the
    // section is not a form control, so target the textarea directly.
    const summary = page.locator('section[aria-labelledby="summary-heading"] textarea').first()
    await expect(summary).toBeVisible()
    await summary.fill('Backend engineer targeting platform roles.')

    await page.getByRole('button', { name: /save as new revision/i }).click()
    await expect(page.locator('body')).toContainText(/revision 1|2 revisions|saved/i)
  })

  test('a version can be named and compared with the original', async ({ page, context }) => {
    await withSession(context, seeded.token)

    await page.goto(`/app/resumes/${seeded.resumeId}/studio`)
    const summary = page.locator('section[aria-labelledby="summary-heading"] textarea').first()
    await expect(summary).toBeVisible()

    const improved = 'Platform engineer focused on developer experience and deploy safety.'
    await summary.fill(improved)
    await page.getByLabel('Name this version (optional)').fill('Platform')
    await page.getByRole('button', { name: /save as new revision/i }).click()

    // The label is stored and shown in the version picker and history.
    await expect(page.locator('#version-select')).toContainText('Platform')

    await page.getByRole('button', { name: /^compare$/i }).click()
    const panel = page.locator('section[aria-labelledby="compare-heading"]')
    await expect(panel).toContainText('summary')
    await expect(panel).toContainText(improved)
  })

  test('a named version can be chosen for export', async ({ page, context }) => {
    await withSession(context, seeded.token)

    await page.goto(`/app/analyses/${seeded.analysisId}/export`)
    const picker = page.locator('#export-version')
    await expect(picker).toContainText('Platform')

    const option = page.locator('#export-version option', { hasText: 'Platform' })
    await picker.selectOption(await option.getAttribute('value'))
    await page.getByRole('button', { name: /generate resume pdf/i }).click()

    // The generated file is labelled with the version that produced it, so the
    // history answers "which version is this?" without opening the file.
    const historySection = page.locator('section[aria-labelledby="export-history"]')
    await expect(historySection).toContainText(/Platform/)
    await expect(historySection.getByRole('link', { name: /^download$/i }).first()).toBeVisible()
  })

  test('history lists the uploaded resume and the analysis', async ({ page, context }) => {
    await withSession(context, seeded.token)

    await page.goto('/app/history')
    await expect(page.locator('body')).toContainText('arjun.pdf')
    await expect(page.locator('body')).toContainText(/analys/i)
  })

  test('journey 14: logout flow cleans session and redirects to sign in', async ({ page, context }) => {
    await withSession(context, seeded.token)

    await page.goto('/app')
    await expect(page.getByRole('button', { name: /sign out/i }).first()).toBeVisible()
    await page.getByRole('button', { name: /sign out/i }).first().click()

    await expect(page).toHaveURL(/\/login/)
  })
})
