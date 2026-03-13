/**
 * 화해 랭킹 카테고리 구조 + 카테고리별 제품 목록 확인
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

  // 랭킹 페이지
  await page.goto('https://www.hwahae.co.kr/rankings', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  // 1. 전체 카테고리 구조
  const categories = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    const d = JSON.parse(el.textContent);
    const props = d.props?.pageProps || {};

    // rankings (테마 목록)
    const rankings = (props.rankings || []).map(r => ({
      id: r.id,
      name: r.shortcut_name,
      english: r.english_name,
      type: r.ranking_type,
    }));

    // rankingsCategories (카테고리 트리)
    const cat = props.rankingsCategories || {};
    const flatCategories = [];
    function flatten(node, depth) {
      flatCategories.push({
        id: node.id,
        name: node.name,
        depth: depth,
        code: node.category_code || null,
        max_rank: node.max_rank || null,
      });
      (node.children || []).forEach(c => flatten(c, depth + 1));
    }
    flatten(cat, 0);

    // 첫 페이지 제품 목록
    const products = props.rankingProducts?.data?.details || [];
    const pagination = props.rankingProducts?.meta?.pagination || {};

    return {
      rankings,
      categories: flatCategories,
      pagination,
      sampleProducts: products.slice(0, 3).map(p => ({
        rank: p.rank,
        brand: p.brand?.name,
        name: p.goods?.name || p.goods?.display_title,
        product_id: p.goods?.product_id,
        price: p.goods?.price,
        image: p.goods?.image_url,
      })),
    };
  });

  console.log('=== 랭킹 테마 ===');
  console.log(JSON.stringify(categories.rankings, null, 2));

  console.log('\n=== 카테고리 트리 ===');
  categories.categories.forEach(c => {
    console.log('  '.repeat(c.depth) + c.name + ' (id:' + c.id + ', code:' + c.code + ', max:' + c.max_rank + ')');
  });

  console.log('\n=== 페이지네이션 ===');
  console.log(JSON.stringify(categories.pagination));

  console.log('\n=== 샘플 제품 (상위 3개) ===');
  console.log(JSON.stringify(categories.sampleProducts, null, 2));

  // 2. 카테고리별 API 호출 시도 (Next.js data route)
  console.log('\n=== 카테고리별 API 테스트 ===');

  // 카테고리 변경 시 API 호출 확인
  const apiCalls = [];
  page.on('response', async (res) => {
    const url = res.url();
    if (url.includes('ranking') && (res.headers()['content-type'] || '').includes('json') && res.status() === 200) {
      try {
        const body = await res.json();
        const details = body.data?.details || body.pageProps?.rankingProducts?.data?.details || [];
        apiCalls.push({
          url: url.slice(0, 150),
          productCount: details.length,
          firstProduct: details[0] ? (details[0].goods?.name || details[0].brand?.name || '?') : 'none',
        });
      } catch (e) {}
    }
  });

  // depth2 카테고리 2개 테스트 (스킨케어, 메이크업)
  const testCats = categories.categories.filter(c => c.depth === 2 && c.code).slice(1, 4);
  for (const cat of testCats) {
    console.log('\n  카테고리: ' + cat.name + ' (id:' + cat.id + ')');
    // 화해 랭킹 카테고리 URL 패턴 시도
    try {
      const url = 'https://www.hwahae.co.kr/rankings?category=' + cat.id;
      await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
      await new Promise(r => setTimeout(r, 2000));
      const result = await page.evaluate(() => {
        const el = document.getElementById('__NEXT_DATA__');
        if (!el) return null;
        const d = JSON.parse(el.textContent);
        const products = d.props?.pageProps?.rankingProducts?.data?.details || [];
        const pagination = d.props?.pageProps?.rankingProducts?.meta?.pagination || {};
        return {
          count: products.length,
          total: pagination.total_count,
          firstProduct: products[0] ? (products[0].goods?.name || '?') : 'none',
          lastProduct: products[products.length-1] ? (products[products.length-1].goods?.name || '?') : 'none',
        };
      });
      console.log('  결과: ' + JSON.stringify(result));
    } catch (e) {
      console.log('  ERROR: ' + e.message.slice(0, 60));
    }
  }

  console.log('\n=== API 호출 (' + apiCalls.length + '개) ===');
  apiCalls.forEach(a => console.log('  ' + a.url));

  await browser.close();
}

main().catch(e => console.error(e.message));
