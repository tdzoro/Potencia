import { Link } from 'react-router-dom'

interface Capability {
  title: string
  body: string
  accent: string
}

const capabilities: Capability[] = [
  {
    title: 'Resume analysis',
    accent: 'from-electric/70 to-violet/40',
    body: 'Section-by-section evaluation of content, structure, language and quantified evidence — with every score traceable to the text that produced it.',
  },
  {
    title: 'ATS compatibility estimate',
    accent: 'from-violet/70 to-cyan/40',
    body: 'How reliably resume software can read the document: extraction fidelity, reading order, structural hazards and date parseability. An estimate, never a guarantee.',
  },
  {
    title: 'Job matching',
    accent: 'from-cyan/70 to-electric/40',
    body: 'Compare a resume against a specific description to separate what is matched, partially matched, absent, or claimed without supporting evidence.',
  },
  {
    title: 'Improvement studio',
    accent: 'from-electric/60 to-cyan/40',
    body: 'Rewrite weak bullets with your approval, keep the original intact, and export a PDF or DOCX that still survives parsing.',
  },
]

const principles: string[] = [
  'Deterministic scoring — identical input, identical score.',
  'Every deduction cites the line that caused it.',
  'No invented achievements, skills or metrics. Ever.',
]

export function LandingPage() {
  return (
    <div className="flex flex-col gap-16 lg:gap-24">
      <section aria-labelledby="hero-heading" className="max-w-3xl">
        <img
          src="/logo.png"
          alt="POTENCIA — Power Your Potential"
          width={1200}
          height={800}
          draggable={false}
          className="h-[112px] w-auto select-none rounded-xl ring-1 ring-line/50 sm:h-[136px]"
        />

        <p className="mt-8 text-xs font-semibold uppercase tracking-[0.28em] text-electric">
          AI Resume Intelligence
        </p>

        <h1
          id="hero-heading"
          className="mt-4 text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl lg:text-6xl"
        >
          Resume feedback that <span className="gradient-text">shows its reasoning.</span>
        </h1>

        <p className="mt-6 text-lg leading-relaxed text-muted">
          POTENCIA reads a resume, reconstructs its structure, and measures it against explicit
          criteria. You get an explainable score, an ATS compatibility estimate, a job-specific
          match, and a prioritized list of fixes — each one attached to the sentence behind it.
        </p>

        <p className="mt-4 text-sm font-medium uppercase tracking-[0.22em] text-muted">
          Beyond Your Resume. Unleash Your Potential.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-3">
          <a href="#capabilities" className="btn-primary">
            See what it measures
          </a>
          <Link to="/status" className="btn-ghost">
            Check system status
          </Link>
        </div>
      </section>

      <section aria-labelledby="capabilities-heading" id="capabilities">
        <div className="flex flex-col gap-2">
          <p className="label">Capabilities</p>
          <h2 id="capabilities-heading" className="text-2xl font-semibold tracking-tight text-ink">
            Four things it refuses to guess at
          </h2>
        </div>

        <ul className="mt-8 grid gap-4 sm:grid-cols-2">
          {capabilities.map((capability) => (
            <li key={capability.title} className="panel group relative overflow-hidden p-6">
              <span
                aria-hidden="true"
                className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r ${capability.accent}`}
              />
              <h3 className="text-base font-semibold text-ink">{capability.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">{capability.body}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="principles-heading" className="panel p-6 sm:p-8">
        <p className="label">Commitments</p>
        <h2 id="principles-heading" className="mt-2 text-2xl font-semibold tracking-tight text-ink">
          Numbers come from rules. Prose comes from models.
        </h2>
        <ul className="mt-6 grid gap-3 sm:grid-cols-3">
          {principles.map((principle) => (
            <li
              key={principle}
              className="rounded-xl border border-line/70 bg-void/50 p-4 text-sm leading-relaxed text-muted"
            >
              {principle}
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="start-heading"
        className="rounded-2xl border border-electric/30 bg-gradient-to-br from-electric/10 via-surface/80 to-violet/10 p-6 sm:p-8"
      >
        <p className="label">Start here</p>
        <h2 id="start-heading" className="mt-2 text-lg font-semibold text-ink">
          Upload a resume, leave with a report you can act on.
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
          PDF or DOCX, up to 5 MiB. POTENCIA extracts the text, rebuilds the sections and scores 27
          criteria across six weighted categories — naming the line behind every deduction.
        </p>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">
          From the report you can paste a job description, accept or reject each recommendation,
          edit your summary and bullets in the studio, compare versions field by field, and export
          a PDF or DOCX. The original parse is never overwritten.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/register" className="btn-primary">
            Create an account
          </Link>
          <Link to="/status" className="btn-ghost">
            Check system status
          </Link>
        </div>
      </section>
    </div>
  )
}
