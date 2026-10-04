import puppeteer from 'puppeteer-core';
import path from 'path';

const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const artifactDir = 'C:\\Users\\iitdc\\.gemini\\antigravity\\brain\\87b6d883-ffbb-464b-9d16-a124cd644d48';

async function testTitleSim() {
  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  page.on('console', msg => console.log('[LOG]:', msg.text()));
  page.on('pageerror', err => console.error('[PAGE ERROR]:', err));

  console.log('Navigating to http://localhost:8000/ ...');
  await page.goto('http://localhost:8000/', { waitUntil: 'networkidle0' });

  console.log('Clicking "Validate Custom Paper / Data"...');
  const customBtn = await page.waitForSelector('xpath///button[contains(., "Validate Custom Paper / Data")]');
  await customBtn.click();
  await new Promise(r => setTimeout(r, 600));

  console.log('Entering Scopus URL for paper 85116424104...');
  const input = await page.waitForSelector('input[placeholder*="scopus.com"]');
  await input.type('https://www.scopus.com/pages/publications/85116424104?origin=resultslist', { delay: 10 });

  console.log('Running validation pipeline...');
  const runBtn = await page.waitForSelector('xpath///button[contains(., "Run Automated Validation Pipeline")]');
  await runBtn.click();

  await page.waitForSelector('xpath///strong[contains(., "99")]', { timeout: 35000 });
  console.log('Results loaded in UI with 99 references!');
  await new Promise(r => setTimeout(r, 800));

  const tableScreenshotPath = path.join(artifactDir, 'test_99_title_sim.png');
  await page.screenshot({ path: tableScreenshotPath });
  console.log('Saved table screenshot to', tableScreenshotPath);

  // Click Inspect on the first row
  console.log('Clicking Inspect on first reference...');
  const inspectBtn = await page.waitForSelector('xpath///button[contains(., "Inspect")]');
  await inspectBtn.click();
  await new Promise(r => setTimeout(r, 1200));

  const screenshotPath = path.join(artifactDir, 'test_title_sim_results.png');
  await page.screenshot({ path: screenshotPath });
  console.log('Saved drawer screenshot to', screenshotPath);

  await browser.close();
}

testTitleSim().catch(err => {
  console.error('Test error:', err);
  process.exit(1);
});
