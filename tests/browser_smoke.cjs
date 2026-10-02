const {chromium} = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const localPython = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.EUREKA_PYTHON || (fs.existsSync(localPython) ? localPython : 'python');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'eureka-browser-'));
const port = process.env.EUREKA_TEST_PORT || '8765';
const base = `http://127.0.0.1:${port}`;
const output = path.join(root, 'test-results');
fs.mkdirSync(output, {recursive:true});
const child = spawn(python, [path.join(__dirname, 'browser_server.py')], {
  cwd:root, env:{...process.env, PYTHONPATH:root, EUREKA_DB:path.join(temporary, 'browser.db'), EUREKA_TEST_PORT:port},
  stdio:['ignore','pipe','pipe']
});
let logs = '', childError;
child.stdout.on('data', d => logs += d);
child.stderr.on('data', d => logs += d);
child.on('error', e => childError=e);
let browser;
const waitFor = async (fn, label) => {
  for(let i=0; i<200; i++) {if(await fn()) return; await new Promise(r=>setTimeout(r,100));}
  throw Error('Timed out: '+label);
};
(async () => {
  await waitFor(async()=>{
    if(childError) throw childError;
    if(child.exitCode !== null) throw Error(logs);
    try {return (await fetch(base+'/api/v1/health')).ok;} catch {return false;}
  }, 'server startup');
  browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000}, acceptDownloads:true});
  const page = await context.newPage();
  const errors=[];
  page.on('pageerror', e=>errors.push(e.message));
  page.on('console', m=>{if(m.type()==='error') errors.push(m.text());});
  await page.goto(base);
  await page.locator('#try-demo').click();
  await page.locator('.card').nth(5).waitFor();
  assert.equal(await page.locator('.card').count(),6);
  await page.locator('.save-btn').first().click();
  await waitFor(async()=>await page.locator('#saved-count').textContent()==='1','bookmark count');
  await page.locator('[data-view="saved"]').click();
  await waitFor(async()=>await page.locator('.card').count()===1,'saved collection');
  await page.locator('.card-title button').first().click();
  await page.locator('#bookmark-note').fill('García — presentation notes');
  await page.locator('#save-note').click();
  await waitFor(async()=>await page.locator('#toast').textContent()==='Record and note saved','note save');
  await page.keyboard.press('Escape');
  await page.reload();
  await page.locator('[data-view="saved"]').click();
  await page.locator('.card-title button').first().click();
  assert.equal(await page.locator('#bookmark-note').inputValue(),'García — presentation notes');
  await page.locator('#close-details').click();
  const downloadPromise=page.waitForEvent('download');
  await page.locator('#export').click();
  const download=await downloadPromise;
  const csv=fs.readFileSync(await download.path(),'utf8');
  assert.match(csv,/bookmark_note/);
  assert.match(csv,/García — presentation notes/);
  await page.locator('[data-view="conference"]').click();
  await waitFor(async()=>await page.locator('.card').count()===5,'conferences');
  await page.locator('#deadline').selectOption('open');
  await waitFor(async()=>await page.locator('.card').count()===3,'deadline filter');
  await page.locator('[data-view="dashboard"]').click();
  await page.locator('.stat').nth(3).waitFor();
  await page.screenshot({path:path.join(output,'desktop-dashboard.png'),fullPage:true});
  await page.locator('[data-view="paper"]').click();
  await page.locator('#mode').selectOption('live');
  await page.locator('.empty').waitFor();
  await page.locator('#query').fill('graph');
  await page.locator('#search-button').click();
  await page.locator('#feedback.warning').waitFor();
  assert.match(await page.locator('#feedback').textContent(),/ARXIV.*timed out/);
  await waitFor(async()=>await page.locator('.card').count()===12,'live results');
  const records=await (await context.request.get(base+'/api/v1/items?page_size=100')).json();
  for(const record of records.items) await context.request.post(base+'/api/v1/bookmarks',{data:{item_id:record.id}});
  await page.locator('[data-view="saved"]').click();
  await waitFor(async()=>await page.locator('#result-count').textContent()==='13','13 saved records');
  await page.locator('#next').click();
  await waitFor(async()=>await page.locator('.card').count()===1,'second page');
  await page.locator('.save-btn').click();
  await waitFor(async()=>await page.locator('.card').count()===12,'last-page removal recovery');
  assert.equal(await page.locator('#page-label').textContent(),'Page 1 of 1');
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-view="paper"]').click();
  await page.screenshot({path:path.join(output,'mobile-papers.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'mobile horizontal overflow');
  await page.locator('.card-title button').first().click();
  await page.locator('dialog[open]').waitFor();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('dialog[open]').count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({browser:'Chromium',desktop:true,mobile:true,notes:true,download:true,deadline_filter:true,partial_failure:true,pagination_recovery:true,errors}));
})().catch(e=>{console.error(e);console.error(logs);process.exitCode=1;}).finally(async()=>{
  if(browser) await browser.close();
  if(child.exitCode===null) {
    const closed=new Promise(resolve=>child.once('exit',resolve));
    child.kill();
    await Promise.race([closed,new Promise(resolve=>setTimeout(resolve,5000))]);
  }
  fs.rmSync(temporary,{recursive:true,force:true,maxRetries:5,retryDelay:200});
});
