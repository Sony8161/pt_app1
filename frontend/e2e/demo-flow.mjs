// End-to-end test of the demo journey through the real stack: browser -> proxy -> Lambda -> PostgreSQL.
//
//   ./bin/demo-postgres.sh && ./bin/start-dev.sh      # the stack (LocalStack), in its own terminal
//   ./bin/demo-ready.sh                               # the sample company and the logins used below
//   cd frontend && npm run e2e                        # ends with a PASS/FAIL line per check; exit code 1 on any FAIL
//   ./bin/demo-ready.sh                               # the test changes data (completes a milestone, archives a project)
//
// BASE_URL changes the site address; SHOTS=<dir> saves a screenshot per step. It also scans the main pages with axe-core
// and fails on serious or critical accessibility problems.
import { createRequire } from 'node:module'
import { chromium } from 'playwright'

const require = createRequire(import.meta.url)
const SHOTS = process.env.SHOTS
const URL = process.env.BASE_URL ?? 'http://localhost:3000'
const browser = await chromium.launch()
const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage()
const log = []
const ok = (name, cond, extra = '') => { log.push(`${cond ? 'PASS' : 'FAIL'}  ${name} ${extra}`); if (!cond) process.exitCode = 1 }

const AXE = require.resolve('axe-core/axe.min.js')
async function scan(name) {
  await page.addScriptTag({ path: AXE })
  const result = await page.evaluate(() => window.axe.run(document, { resultTypes: ['violations'] }))
  const bad = result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  ok(`accessibility (axe): ${name}`, bad.length === 0, bad.map((v) => `${v.id} x${v.nodes.length}`).join(', '))
}
const shot = (n) => (SHOTS ? page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true }) : Promise.resolve())
const iso = (offset) => { const d = new Date(); d.setDate(d.getDate() + offset); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
const projectLink = (n) => page.locator('a[href^="/projects/"]', { has: page.locator('h6', { hasText: n }) }).first()
const card = (name) => page.locator('div.MuiPaper-root').filter({ has: page.getByRole('heading', { name, exact: true }) }).last()

async function signIn(u, p) {
  await page.goto(URL + '/login')
  await page.getByLabel('Username').fill(u); await page.getByLabel('Password').fill(p)
  await page.getByRole('button', { name: 'Sign in' }).click()
}
async function signOut() { await page.getByRole('button', { name: 'Sign out' }).first().click(); await page.waitForURL('**/login') }

// ACT 1 admin
await page.goto(URL + '/login')
await page.getByLabel('Username').waitFor()
await scan('sign-in page')
await signIn('admin1', 'Demo1234!')
await page.getByText('Projects, most urgent first').waitFor()
const titles = await page.locator('a[href^="/projects/"] h6').allInnerTexts()
ok('admin: projects ranked urgent first', titles.join('|') === 'Mobile App Launch|Data Platform Migration|Website Redesign|Customer Portal', titles.join('|'))
await shot('a1-admin-dashboard')
await scan('dashboard')
await projectLink('Data Platform Migration').click()
await page.getByText('Why this project is at risk').waitFor()
const body1 = await page.locator('main').innerText()
ok('admin: at-risk reasons shown', /ahead of the calendar/.test(body1) && /Planned staffing will cost/.test(body1))
await shot('a2-at-risk-detail')
await scan('project detail')
await signOut()

// ACT 2 employee
await signIn('alex01', 'Demo1234!')
await page.getByText('My milestones').waitFor()
const emp = await page.locator('body').innerText()
ok('employee: sees Build, 1 of 2 deliverables, no dollar amounts', /Build/.test(emp) && /1 of 2 deliverables done/.test(emp) && !/\$/.test(emp))
await shot('b1-employee')
await scan('my work')
await signOut()

// ACT 3 manager
await signIn('maria1', 'Demo1234!')
await page.getByText('Projects, most urgent first').waitFor()
const mt = await page.locator('a[href^="/projects/"] h6').allInnerTexts()
ok('manager: sees only own projects', mt.sort().join('|') === 'Customer Portal|Website Redesign', mt.join('|'))
await projectLink('Website Redesign').click()
await page.getByRole('heading', { name: 'Build', exact: true }).waitFor()
await shot('c1-website')
await scan('manager project page')
// overlap refused
await card('Launch').getByRole('button', { name: 'Assign a person' }).click()
await page.getByLabel(/^Employee/).click(); await page.getByRole('option', { name: /Sofia Rossi/ }).click()
await page.getByRole('button', { name: 'Assign', exact: true }).click()
await page.getByRole('dialog').getByText(/already on milestone 'Discovery' of 'Customer Portal'/).waitFor()
ok('manager: double booking refused with a named clash', true)
await shot('c2-overlap-refused')
await page.getByRole('button', { name: 'Cancel' }).click()
// free person works
await card('Launch').getByRole('button', { name: 'Assign a person' }).click()
await page.getByLabel(/^Employee/).click(); await page.getByRole('option', { name: /Priya Shah/ }).click()
await page.getByRole('button', { name: 'Assign', exact: true }).click()
await card('Launch').getByText(/Priya Shah/).waitFor()
ok('manager: free person assigned', true)
await shot('c3-assigned')
// completion refused then succeeds
await card('Build').getByRole('button', { name: 'Complete milestone' }).click()
await page.getByRole('button', { name: 'Sign off and complete' }).click()
await page.getByRole('dialog').getByText(/not done yet: Dashboard/).waitFor()
ok('manager: completion refused while Dashboard is open', true)
await shot('c4-complete-refused')
await page.getByRole('button', { name: 'Cancel' }).click()
await card('Build').getByRole('checkbox', { name: 'Dashboard' }).click()
await page.waitForFunction(() => document.body.innerText.includes('2 of 2 done'))
await card('Build').getByRole('button', { name: 'Complete milestone' }).click()
await page.getByLabel('Review note').fill('Reviewed with the client; both screens signed off')
await page.getByRole('button', { name: 'Sign off and complete' }).click()
await page.getByRole('heading', { name: 'Build', exact: true }).waitFor({ state: 'detached' })
await page.waitForTimeout(500)
const tiles = await page.locator('main').innerText()
ok('manager: milestone completed and archived, progress counts it', /2 of 3/.test(tiles), (tiles.match(/\d of \d/g) || []).join(','))
await shot('c5-completed')
await signOut()

// ACT 4 new hire
await signIn('nina01', 'Welcome123!')
await page.waitForURL('**/change-password')
await page.getByLabel('Current password').fill('Welcome123!')
await page.getByLabel(/^New password/).fill('Welcome456!'); await page.getByLabel('Repeat new password').fill('Welcome456!')
await shot('d1-change-password')
await page.getByRole('button', { name: 'Save new password' }).click()
await page.waitForURL('**/my-work')
ok('new hire: forced to choose a password, then lands on My work', true)
await signOut()

// ACT 5 admin archive + restore
await signIn('admin1', 'Demo1234!')
await page.getByText('Projects, most urgent first').waitFor()
await page.getByRole('link', { name: 'People', exact: true }).first().click()
await page.getByRole('heading', { name: 'People', exact: true }).waitFor()
await page.getByRole('cell', { name: /Maria Lopez/ }).first().waitFor()
await scan('people page')
await page.getByRole('link', { name: 'Dashboard', exact: true }).first().click()
await page.getByText('Projects, most urgent first').waitFor()
await projectLink('Website Redesign').click()
await page.getByRole('heading', { name: 'Build', exact: true }).waitFor()
ok('admin: still sees the completed milestone, marked archived', await page.getByText('Completed, archived').count() > 0)
await shot('e1-admin-sees-archived-milestone')
await page.getByRole('link', { name: 'Projects', exact: true }).first().click()
await projectLink('Customer Portal').click()
await page.getByRole('button', { name: 'Archive' }).click()
await page.getByRole('button', { name: 'Archive', exact: true }).last().click()
await page.waitForTimeout(600)
await page.getByRole('link', { name: 'Archive' }).first().click()
await page.getByRole('cell', { name: 'Customer Portal' }).waitFor()
await shot('e2-archive-page')
await page.getByRole('button', { name: 'Restore' }).first().click()
await page.getByText('No archived projects.').waitFor()
ok('admin: archived project restored from the Archive page', true)
console.log(log.join('\n'))
await browser.close()
if (process.exitCode) console.error('E2E FAILED')
