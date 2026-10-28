import { mkdirSync } from 'node:fs'
import { expect, test, type FrameLocator, type Page } from '@playwright/test'

/**
 * Not a test: records the README animation. Two same-site origins give two
 * independent sessions side by side in one page. Run with
 *   RECORD_DEMO=<frames dir> npx playwright test e2e/record-demo.spec.ts
 * then assemble the PNG frames with ffmpeg (see docs/screenshots/README.md).
 */
const OUT = process.env.RECORD_DEMO
test.skip(!OUT, 'Set RECORD_DEMO to a frames directory to record the demo animation.')

const SHELL = (left: string, right: string) => `<!doctype html><html><head><meta charset="utf-8"><style>
  html, body { margin: 0; height: 100%; background: #e6ebf2; font-family: -apple-system, system-ui, sans-serif; }
  .wrap { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 14px; height: calc(100% - 28px); }
  .win { display: flex; flex-direction: column; min-width: 0; background: #fff; border-radius: 12px; box-shadow: 0 10px 34px rgba(20,30,50,.18); overflow: hidden; }
  .bar { display: flex; align-items: center; gap: 8px; padding: 9px 14px; background: #f3f5f8; border-bottom: 1px solid #dfe4ea; font-size: 14px; color: #445; }
  .dots span { display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 5px; background: #d9dee5; }
  .bar strong { margin-left: auto; color: #223; }
  iframe { flex: 1; width: 100%; border: 0; }
</style></head><body><div class="wrap">
  <div class="win"><div class="bar"><span class="dots"><span></span><span></span><span></span></span><strong>Mika's window</strong></div><iframe id="a" src="${left}"></iframe></div>
  <div class="win"><div class="bar"><span class="dots"><span></span><span></span><span></span></span><strong>Jonas's window</strong></div><iframe id="b" src="${right}"></iframe></div>
</div></body></html>`

let shot = 0
async function frame(page: Page, hold: number) {
  shot += 1
  await page.screenshot({ path: `${OUT}/${String(shot).padStart(2, '0')}-${hold}.png` })
}

async function live(frame: FrameLocator) {
  await expect(frame.getByRole('status').filter({ hasText: /^Live$/ })).toBeVisible({ timeout: 20_000 })
}

test('record the two-window demo', async ({ page }) => {
  mkdirSync(OUT!, { recursive: true })
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.setContent(SHELL('http://127.0.0.1:5175/demo?as=mika', 'http://localhost:5175/demo?as=jonas'))
  const mika = page.frameLocator('#a')
  const jonas = page.frameLocator('#b')
  await live(mika)
  await live(jonas)
  // The "Demo as …" links are for visitors; the recording shows two plain windows.
  for (const child of page.frames().filter((f) => f !== page.mainFrame())) {
    await child.evaluate(() => { sessionStorage.removeItem('triptogether.demoMember'); location.reload() })
  }
  await live(mika)
  await live(jonas)
  await mika.getByRole('tab', { name: 'Itinerary' }).click()
  await jonas.getByRole('tab', { name: 'Itinerary' }).click()
  for (const win of [mika, jonas]) {
    await win.getByRole('article').filter({ hasText: 'Torii gates at sunrise' }).scrollIntoViewIfNeeded()
  }
  await page.waitForTimeout(600)
  await frame(page, 2000)

  const title = mika.getByLabel('Title')
  await title.click()
  for (const chunk of ['Matcha ', 'break ', 'at Ippodo']) {
    await title.pressSequentially(chunk, { delay: 40 })
  }
  await frame(page, 1400)
  await mika.getByRole('button', { name: 'Add item' }).click()
  const arrived = jonas.getByRole('article').filter({ hasText: 'Matcha break at Ippodo' })
  await expect(arrived).toBeVisible()
  await expect(jonas.getByRole('status').filter({ hasText: 'mika_demo added an itinerary item.' })).toBeVisible()
  await arrived.scrollIntoViewIfNeeded()
  await mika.getByRole('article').filter({ hasText: 'Matcha break at Ippodo' }).scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await frame(page, 3000)

  await jonas.getByRole('tab', { name: 'Balances' }).click()
  await expect(jonas.getByText(/transfers settle 3 members, the fewest possible/)).toBeVisible()
  await mika.getByRole('tab', { name: 'Expenses' }).click()
  await expect(mika.getByText(/Split by shares/)).toBeVisible()
  await page.waitForTimeout(500)
  await frame(page, 3500)
})
