/**
 * 화해 Next.js data route 직접 호출 테스트
 * /_next/data/{buildId}/rankings.json 패턴
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

  // 세션 + buildId 획득
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  const buildId = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    return JSON.parse(el.textContent).buildId;
  });
  console.log('buildId: ' + buildId);

  // 모든 gateway API 호출 캡처
  const allApis = [];
  page.on('response', async (res) => {
    const url = res.url();
    if (url.includes('gateway.hwahae') && res.status() === 200) {
      try {
        const ct = res.headers()['content-type'] || '';
        if (ct.includes('json')) {
          const body = await res.json();
          allApis.push({ url, bodyKeys: Object.keys(body) });
        }
      } catch(e) {}
    }
  });

  // 랭킹 페이지 접속 (gateway API 캡처)
  await page.goto('https://www.hwahae.co.kr/rankings', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));

  console.log('\n=== Gateway API 캡처 ===');
  allApis.forEach(a => console.log('  ' + a.url.slice(0, 150) + ' -> ' + a.bodyKeys.join(',')));

  // Next.js data route 직접 호출 테스트
  console.log('\n=== Next.js data route 테스트 ===');

  // 카테고리별 랭킹 (카테고리 ID로 데이터 요청)
  const testUrls = [
    // 기본 랭킹
    'https://www.hwahae.co.kr/_next/data/' + buildId + '/rankings.json',
    // 카테고리 ID 파라미터
    'https://www.hwahae.co.kr/_next/data/' + buildId + '/rankings.json?ranking_id=1&category_id=5105',
    'https://www.hwahae.co.kr/_next/data/' + buildId + '/rankings.json?ranking_id=1&category_id=5103',
  ];

  for (const url of testUrls) {
    console.log('\n  URL: ' + url.slice(url.indexOf('rankings')));
    try {
      const res = await page.evaluate(async (fetchUrl) => {
        const r = await fetch(fetchUrl);
        if (!r.ok) return { status: r.status };
        const data = await r.json();
        const props = data.pageProps || {};
        const products = props.rankingProducts?.data?.details || [];
        const pagination = props.rankingProducts?.meta?.pagination || {};
        return {
          status: r.status,
          pagePropsKeys: Object.keys(props),
          productCount: products.length,
          total: pagination.total_count,
          page: pagination.page,
          first: products[0] ? { brand: products[0].brand?.name, name: products[0].goods?.name?.slice(0, 30) } : null,
          last: products[products.length-1] ? { brand: products[products.length-1].brand?.name, name: products[products.length-1].goods?.name?.slice(0, 30) } : null,
        };
      }, url);
      console.log('  ' + JSON.stringify(res));
    } catch (e) {
      console.log('  ERROR: ' + e.message.slice(0, 80));
    }
  }

  // gateway API 직접 호출 시도
  console.log('\n=== Gateway API 직접 호출 ===');
  const gatewayTests = [
    'https://gateway.hwahae.co.kr/v14/rankings/trending/details?page=1&page_size=20',
    'https://gateway.hwahae.co.kr/v14/rankings/category/details?category_id=5105&page=1&page_size=50',
    'https://gateway.hwahae.co.kr/v14/rankings/details?ranking_id=1&category_id=5105&page=1&page_size=50',
  ];

  for (const url of gatewayTests) {
    console.log('\n  ' + url.slice(url.indexOf('/v14/')));
    try {
      const res = await page.evaluate(async (fetchUrl) => {
        const r = await fetch(fetchUrl);
        if (!r.ok) return { status: r.status, statusText: r.statusText };
        const data = await r.json();
        const str = JSON.stringify(data);
        return {
          status: r.status,
          keys: Object.keys(data),
          size: str.length,
          hasDetails: str.includes('details'),
          sample: str.slice(0, 300),
        };
      }, url);
      console.log('  ' + JSON.stringify(res));
    } catch (e) {
      console.log('  ERROR: ' + e.message.slice(0, 80));
    }
  }

  await browser.close();
}

main().catch(e => console.error(e.message));
