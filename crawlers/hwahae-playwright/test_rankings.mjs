/**
 * 화해 랭킹 페이지 구조 확인
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

  // API 응답 캡처
  const apis = [];
  page.on('response', async (res) => {
    const url = res.url();
    if (url.includes('hwahae') && (res.headers()['content-type'] || '').includes('json') && res.status() === 200) {
      try {
        const body = await res.json();
        apis.push({ url: url.slice(0, 120), keys: Object.keys(body).slice(0, 10) });
      } catch (e) {}
    }
  });

  // 세션
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  // 랭킹 페이지 시도
  const urls = [
    'https://www.hwahae.co.kr/rankings',
    'https://www.hwahae.co.kr/rankings/products',
    'https://www.hwahae.co.kr/ranking',
  ];

  for (const url of urls) {
    console.log('\n=== ' + url + ' ===');
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
      await new Promise(r => setTimeout(r, 3000));

      const result = await page.evaluate(() => {
        const el = document.getElementById('__NEXT_DATA__');
        if (!el) return { error: 'no __NEXT_DATA__', title: document.title };
        const d = JSON.parse(el.textContent);
        const props = d.props?.pageProps || {};
        const output = {
          title: document.title,
          pagePropsKeys: Object.keys(props),
        };
        // 제품 목록 찾기
        for (const key of Object.keys(props)) {
          const val = props[key];
          if (val && typeof val === 'object') {
            const str = JSON.stringify(val).slice(0, 300);
            output['prop_' + key] = {
              type: Array.isArray(val) ? 'array(' + val.length + ')' : 'object',
              keys: typeof val === 'object' && !Array.isArray(val) ? Object.keys(val).slice(0, 10) : undefined,
              sample: str,
            };
          }
        }
        // 제품 링크 수
        output.productLinks = document.querySelectorAll('a[href*="/products/"]').length;
        return output;
      });
      console.log(JSON.stringify(result, null, 2));
    } catch (e) {
      console.log('ERROR: ' + e.message.slice(0, 80));
    }
  }

  // 카테고리별 검색도 시도
  console.log('\n=== 카테고리별 검색 (토너 vs 크림) ===');
  for (const q of ['토너', '크림', '선크림']) {
    await page.goto('https://www.hwahae.co.kr/search?query=' + encodeURIComponent(q), { waitUntil: 'networkidle', timeout: 15000 });
    await new Promise(r => setTimeout(r, 3000));
    const result = await page.evaluate(() => {
      const el = document.getElementById('__NEXT_DATA__');
      if (!el) return null;
      const d = JSON.parse(el.textContent);
      const props = d.props?.pageProps || {};
      const trends = props.goodsTrends?.data?.trends || [];
      return {
        trendCount: trends.length,
        firstProduct: trends[0] ? (trends[0].product?.name || trends[0].name || '?') : 'none',
        lastProduct: trends[trends.length-1] ? (trends[trends.length-1].product?.name || '?') : 'none',
        ids: trends.map(t => t.product?.id || t.goods_seq).slice(0, 5),
      };
    });
    console.log(q + ': ' + JSON.stringify(result));
  }

  console.log('\n=== API 응답 (' + apis.length + '개) ===');
  apis.forEach(a => console.log('  ' + a.url + ' -> ' + a.keys.join(',')));

  await browser.close();
}

main().catch(e => console.error(e.message));
