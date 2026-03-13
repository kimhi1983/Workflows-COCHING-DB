/**
 * 화해 랭킹 페이지네이션 + 카테고리 변경 방법 탐색
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
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  const buildId = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    return el ? JSON.parse(el.textContent).buildId : null;
  });

  // 1. 페이지네이션 테스트
  console.log('=== 페이지네이션 테스트 ===');
  for (let p = 1; p <= 3; p++) {
    const url = 'https://www.hwahae.co.kr/_next/data/' + buildId + '/rankings.json?page=' + p;
    const res = await page.evaluate(async (fetchUrl) => {
      const r = await fetch(fetchUrl);
      const data = await r.json();
      const products = data.pageProps?.rankingProducts?.data?.details || [];
      const pagination = data.pageProps?.rankingProducts?.meta?.pagination || {};
      return {
        page: pagination.page,
        count: products.length,
        total: pagination.total_count,
        first: products[0]?.goods?.name?.slice(0, 30),
        last: products[products.length-1]?.goods?.name?.slice(0, 30),
        ids: products.map(p => p.goods?.product_id).slice(0, 3),
      };
    }, url);
    console.log('  page ' + p + ': ' + JSON.stringify(res));
  }

  // 2. 랭킹 페이지에서 실제 카테고리 선택 시 URL 변화 확인
  console.log('\n=== 랭킹 URL 패턴 확인 ===');
  await page.goto('https://www.hwahae.co.kr/rankings', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  // 페이지 내부 라우팅 확인 (Next.js router)
  const routerInfo = await page.evaluate(() => {
    // Next.js router에서 현재 query 확인
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    const d = JSON.parse(el.textContent);
    return {
      page: d.page,
      query: d.query,
      buildId: d.buildId,
      runtimeConfig: d.runtimeConfig ? Object.keys(d.runtimeConfig) : null,
    };
  });
  console.log('Router: ' + JSON.stringify(routerInfo));

  // 3. 다양한 URL 패턴 시도
  console.log('\n=== URL 패턴 탐색 ===');
  const patterns = [
    '/rankings?ranking_detail_id=5105',
    '/rankings?themeId=1',
    '/rankings?theme=category',
    '/rankings?detailId=5105',
    '/rankings/category',
    '/rankings/trending',
    '/rankings/skin',
  ];

  for (const pattern of patterns) {
    const url = 'https://www.hwahae.co.kr/_next/data/' + buildId + pattern.replace('/rankings', '/rankings.json');
    try {
      const res = await page.evaluate(async (fetchUrl) => {
        const r = await fetch(fetchUrl);
        if (!r.ok) return { status: r.status };
        const data = await r.json();
        const products = data.pageProps?.rankingProducts?.data?.details || [];
        return {
          count: products.length,
          first: products[0]?.goods?.name?.slice(0, 30) || 'none',
        };
      }, url);
      console.log('  ' + pattern + ' -> ' + JSON.stringify(res));
    } catch (e) {
      console.log('  ' + pattern + ' -> ERROR: ' + e.message.slice(0, 50));
    }
  }

  // 4. 제품 ID로 직접 상세 페이지 (이미 작동 확인됨) — 몇 개나 빠르게 수집 가능한지 체크
  console.log('\n=== 제품 상세 직접 접근 테스트 (product_id) ===');
  // 랭킹에서 얻은 product_id들
  const productIds = await page.evaluate(async (fetchUrl) => {
    const r = await fetch(fetchUrl);
    const data = await r.json();
    const products = data.pageProps?.rankingProducts?.data?.details || [];
    return products.map(p => p.goods?.product_id).filter(Boolean);
  }, 'https://www.hwahae.co.kr/_next/data/' + buildId + '/rankings.json');

  console.log('  랭킹 제품 IDs (' + productIds.length + '개): ' + productIds.join(', '));

  // 제품 상세 페이지 (Next.js data route)
  const pid = productIds[5]; // 6번째 제품
  const detailUrl = 'https://www.hwahae.co.kr/_next/data/' + buildId + '/products/' + pid + '.json';
  console.log('\n  상세 data route: ' + detailUrl.slice(detailUrl.indexOf('/products/')));
  const detail = await page.evaluate(async (fetchUrl) => {
    const r = await fetch(fetchUrl);
    if (!r.ok) return { status: r.status };
    const data = await r.json();
    const props = data.pageProps || {};
    const ing = props.productIngredientInfoData;
    return {
      keys: Object.keys(props),
      hasIngredients: !!(ing?.ingredients?.length),
      ingredientCount: ing?.ingredients?.length || 0,
      firstIng: ing?.ingredients?.[0]?.korean?.slice(0, 20) || 'none',
    };
  }, detailUrl);
  console.log('  결과: ' + JSON.stringify(detail));

  await browser.close();
}

main().catch(e => console.error(e.message));
