import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0', locale: 'ko-KR' });
const page = await ctx.newPage();

// 모든 hwahae API 요청/응답 캡처
const responses = [];
page.on('response', async (r) => {
  const u = r.url();
  if (u.includes('hwahae') && !u.includes('.js') && !u.includes('.css') &&
      !u.includes('.png') && !u.includes('.jpg') && !u.includes('.svg') &&
      !u.includes('.woff') && !u.includes('analytics') && !u.includes('awswaf')) {
    const ct = r.headers()['content-type'] || '';
    responses.push({ url: u, status: r.status(), ct });
    if (ct.includes('json')) {
      try {
        const body = await r.json();
        console.log('JSON API: ' + u);
        console.log('  body keys: ' + Object.keys(body).join(', '));
        const s = JSON.stringify(body);
        if (s.includes('ingredient') || s.includes('성분')) {
          console.log('  *** CONTAINS INGREDIENTS ***');
          console.log('  ' + s.slice(0, 500));
        }
      } catch (e) {}
    }
  }
});

await page.goto('https://www.hwahae.co.kr/products/2113285', { waitUntil: 'networkidle', timeout: 30000 });
await new Promise(r => setTimeout(r, 5000));

// 전성분 탭 클릭 시도
const clicked = await page.evaluate(() => {
  const elements = document.querySelectorAll('button, a, span, div, li, p');
  for (const el of elements) {
    const text = el.textContent?.trim() || '';
    if (text === '전성분' || text === '성분' || text.includes('전성분')) {
      el.click();
      return 'clicked: ' + text;
    }
  }
  return 'no ingredient tab found';
});
console.log('\nTab click: ' + clicked);
await new Promise(r => setTimeout(r, 3000));

// HTML에서 전성분 관련 텍스트 탐색
const ingText = await page.evaluate(() => {
  const body = document.body.innerText;
  const idx = body.indexOf('전성분');
  if (idx >= 0) {
    return 'FOUND at idx ' + idx + ': ...' + body.slice(idx, idx + 300);
  }
  // 성분 단어 탐색
  const idx2 = body.indexOf('성분');
  if (idx2 >= 0) {
    return 'FOUND 성분 at idx ' + idx2 + ': ...' + body.slice(idx2, idx2 + 300);
  }
  return 'NOT FOUND in body text (len=' + body.length + ')';
});
console.log('\nIngredient text search: ' + ingText);

console.log('\n=== All hwahae responses (' + responses.length + ') ===');
responses.forEach(r => console.log(r.status + ' ' + r.ct.slice(0, 30) + ' ' + r.url.slice(0, 120)));

await browser.close();
