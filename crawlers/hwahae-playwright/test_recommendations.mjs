/**
 * 화해 상세 페이지에서 추천 제품 ID 구조 확인
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

  // 상세 페이지 접속
  const testId = '2113285'; // 아누아 PDRN 세럼
  console.log('=== 상세 페이지 분석: product ' + testId + ' ===');
  await page.goto('https://www.hwahae.co.kr/products/' + testId, { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));

  // __NEXT_DATA__ 전체 pageProps 키 확인
  const analysis = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return { error: 'no __NEXT_DATA__' };
    const d = JSON.parse(el.textContent);
    const props = d.props?.pageProps || {};
    const result = { pagePropsKeys: Object.keys(props) };

    // 각 키의 구조 분석
    for (const key of Object.keys(props)) {
      const val = props[key];
      if (val && typeof val === 'object') {
        const str = JSON.stringify(val);
        result['key_' + key] = {
          type: Array.isArray(val) ? 'array(' + val.length + ')' : 'object',
          size: str.length,
          hasProductId: str.includes('product_id'),
          hasProducts: str.includes('"products"') || str.includes('"goods"'),
        };
        // product_id가 포함된 키 상세 분석
        if (str.includes('product_id') || str.includes('"goods"')) {
          result['detail_' + key] = str.slice(0, 500);
        }
      }
    }

    // DOM에서 다른 제품 링크 확인
    const links = document.querySelectorAll('a[href*="/products/"]');
    const otherIds = new Set();
    links.forEach(l => {
      const m = l.href?.match(/products\/(\d+)/);
      if (m && m[1] !== '2113285') otherIds.add(m[1]);
    });
    result.otherProductLinks = Array.from(otherIds);

    return result;
  });

  console.log('\npageProps 키: ' + analysis.pagePropsKeys.join(', '));

  for (const key of Object.keys(analysis)) {
    if (key.startsWith('key_')) {
      const info = analysis[key];
      const flag = (info.hasProductId || info.hasProducts) ? ' *** PRODUCTS ***' : '';
      console.log('\n  ' + key.slice(4) + ': ' + info.type + ' (size:' + info.size + ')' + flag);
    }
  }

  for (const key of Object.keys(analysis)) {
    if (key.startsWith('detail_')) {
      console.log('\n  [' + key.slice(7) + '] ' + analysis[key]);
    }
  }

  console.log('\n  다른 제품 링크 (DOM): ' + analysis.otherProductLinks?.length + '개');
  console.log('  IDs: ' + (analysis.otherProductLinks || []).slice(0, 20).join(', '));

  // 스크롤해서 더 많은 추천 로드
  console.log('\n=== 스크롤 후 추가 제품 확인 ===');
  for (let i = 0; i < 5; i++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await new Promise(r => setTimeout(r, 2000));
  }

  const afterScroll = await page.evaluate(() => {
    const links = document.querySelectorAll('a[href*="/products/"]');
    const ids = new Set();
    links.forEach(l => {
      const m = l.href?.match(/products\/(\d+)/);
      if (m) ids.add(m[1]);
    });
    return Array.from(ids);
  });
  console.log('  스크롤 후 전체 제품 ID: ' + afterScroll.length + '개');
  console.log('  IDs: ' + afterScroll.slice(0, 30).join(', '));

  await browser.close();
}

main().catch(e => console.error(e.message));
