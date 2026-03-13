/**
 * 화해 랭킹 API 인터셉트 — 카테고리 클릭 시 호출되는 API 확인
 */
import { chromium } from 'playwright';

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR',
    viewport: { width: 1440, height: 900 },
  });
  await ctx.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
  });

  const page = await ctx.newPage();

  // 세션
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  // API 인터셉트
  const apis = [];
  page.on('response', async (res) => {
    const url = res.url();
    const ct = res.headers()['content-type'] || '';
    if (ct.includes('json') && res.status() === 200 && (url.includes('ranking') || url.includes('gateway'))) {
      try {
        const body = await res.json();
        const str = JSON.stringify(body);
        apis.push({
          url,
          size: str.length,
          hasProducts: str.includes('product_id') || str.includes('goods'),
          sample: str.slice(0, 200),
        });
        if (str.includes('product_id') || str.includes('goods')) {
          console.log('  [API] ' + url.slice(0, 120));
          console.log('    size:' + str.length + ' hasGoods:true');
        }
      } catch (e) {}
    }
  });

  // 랭킹 페이지
  await page.goto('https://www.hwahae.co.kr/rankings', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  // "카테고리별" 탭 클릭
  console.log('\n=== 카테고리별 탭 클릭 ===');
  const clicked = await page.evaluate(() => {
    const btns = document.querySelectorAll('button, a, span, div');
    for (const btn of btns) {
      const text = (btn.textContent || '').trim();
      if (text === '카테고리별') {
        btn.click();
        return 'clicked: ' + text;
      }
    }
    return 'not found';
  });
  console.log(clicked);
  await new Promise(r => setTimeout(r, 3000));

  // 서브카테고리 목록 확인
  const subCats = await page.evaluate(() => {
    const items = [];
    const btns = document.querySelectorAll('button, a, li');
    for (const btn of btns) {
      const text = (btn.textContent || '').trim();
      if (['스킨케어', '클렌징/필링', '마스크/팩', '선케어', '베이스메이크업',
           '아이메이크업', '립메이크업', '바디', '헤어', '네일', '향수'].includes(text)) {
        items.push(text);
      }
    }
    return items;
  });
  console.log('서브카테고리: ' + subCats.join(', '));

  // 스킨케어 클릭
  console.log('\n=== 스킨케어 클릭 ===');
  apis.length = 0;
  await page.evaluate(() => {
    const btns = document.querySelectorAll('button, a, li, span');
    for (const btn of btns) {
      const text = (btn.textContent || '').trim();
      if (text === '스킨케어' && btn.tagName !== 'SPAN') {
        btn.click();
        return true;
      }
    }
    return false;
  });
  await new Promise(r => setTimeout(r, 3000));

  // 스킨/토너 클릭
  console.log('\n=== 스킨/토너 클릭 ===');
  apis.length = 0;
  await page.evaluate(() => {
    const btns = document.querySelectorAll('button, a, li, span');
    for (const btn of btns) {
      const text = (btn.textContent || '').trim();
      if (text === '스킨/토너') {
        btn.click();
        return true;
      }
    }
    return false;
  });
  await new Promise(r => setTimeout(r, 5000));

  console.log('\nAPI 호출 (' + apis.length + '개):');
  apis.forEach(a => console.log('  ' + a.url.slice(0, 150) + ' (size:' + a.size + ')'));

  // __NEXT_DATA__ 다시 확인 (SPA 라우트 변경 후)
  const afterClick = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    const d = JSON.parse(el.textContent);
    const products = d.props?.pageProps?.rankingProducts?.data?.details || [];
    return {
      url: location.href,
      productCount: products.length,
      first: products[0] ? { brand: products[0].brand?.name, name: products[0].goods?.name, pid: products[0].goods?.product_id } : null,
    };
  });
  console.log('\n페이지 상태: ' + JSON.stringify(afterClick));

  // DOM에서 제품 목록 추출
  const domProducts = await page.evaluate(() => {
    const items = [];
    // 제품 링크 또는 카드
    const links = document.querySelectorAll('a[href*="/products/"]');
    links.forEach(link => {
      const m = link.href?.match(/products\/(\d+)/);
      if (m) {
        const text = link.textContent?.trim().slice(0, 80) || '';
        const img = link.querySelector('img');
        items.push({ id: m[1], text, img: img?.src?.slice(0, 60) || '' });
      }
    });
    return items.slice(0, 5);
  });
  console.log('\nDOM 제품: ' + JSON.stringify(domProducts, null, 2));

  console.log('\n=== 전체 API 기록 (' + apis.length + '개) ===');
  apis.forEach(a => {
    console.log('  URL: ' + a.url);
    console.log('  sample: ' + a.sample.slice(0, 150));
    console.log();
  });

  await browser.close();
}

main().catch(e => console.error(e.message));
