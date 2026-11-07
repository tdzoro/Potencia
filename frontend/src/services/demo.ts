/**
 * Demo mode.
 *
 * Off unless `VITE_DEMO_MODE=1` at build time. When it is on, the landing page
 * links to a sign-in form pre-filled with an account seeded by
 * `scripts/seed_demo.py`. The credentials are not secrets — they are a shared
 * account whose only purpose is to show a finished report — but they are still
 * behind a build flag so a normal deployment never advertises an account it
 * may not have.
 */
const env = import.meta.env

export const demoEnabled = env.VITE_DEMO_MODE === '1'
export const demoEmail = env.VITE_DEMO_EMAIL ?? 'demo@potencia.app'
export const demoPassword = env.VITE_DEMO_PASSWORD ?? 'potencia-demo-2026'
export const demoLoginPath = '/login?demo=1'
