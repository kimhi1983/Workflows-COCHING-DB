/**
 * 상세 페이지의 관련 제품 + 함께 구매 제품 ID 추출
 */
import { chromium } from 'playwright';

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR', viewport: { width: 1440, height: 900 },
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

  // 2개 제품의 관련 제품 확인
  for (const pid of ['2113285', '1984011']) {
    console.log('\n=== product ' + pid + ' ===');
    await page.goto('https://www.hwahae.co.kr/products/' + pid, { waitUntil: 'networkidle', timeout: 30000 });
    await new Promise(r => setTimeout(r, 4000));

    const data = await page.evaluate((currentPid) => {
      const el = document.getElementById('__NEXT_DATA__');
      if (!el) return null;
      const d = JSON.parse(el.textContent);
      const props = d.props?.pageProps || {};
      const result = { relatedIds: [], pairIds: [], goodsIds: [] };

      // relationGoodsData — 관련 제품
      if (Array.isArray(props.relationGoodsData)) {
        for (const r of props.relationGoodsData) {
          const str = JSON.stringify(r);
          // product_id 패턴 찾기
          const matches = str.match(/"product_id"\s*:\s*(\d+)/g) || [];
          matches.forEach(m => {
            const id = m.match(/(\d+)/)[0];
            if (id !== currentPid) result.relatedIds.push(id);
          });
          // goods_id도 찾기
          const goodsMatches = str.match(/"id"\s*:\s*(\d+)/g) || [];
          goodsMatches.forEach(m => {
            const id = m.match(/(\d+)/)[0];
            if (parseInt(id) > 100000) result.goodsIds.push(id);
          });
        }
        result.relationSample = JSON.stringify(props.relationGoodsData).slice(0, 800);
      }

      // productGoodsPairData — 함께 구매 제품
      if (props.productGoodsPairData) {
        const str = JSON.stringify(props.productGoodsPairData);
        const matches = str.match(/"product_id"\s*:\s*(\d+)/g) || [];
        matches.forEach(m => {
          const id = m.match(/(\d+)/)[0];
          if (id !== currentPid) result.pairIds.push(id);
        });
        result.pairSample = str.slice(0, 800);
      }

      // goodsProductsData에서도 관련 제품 ID
      if (props.goodsProductsData) {
        const str = JSON.stringify(props.goodsProductsData);
        const matches = str.match(/"product_id"\s*:\s*(\d+)/g) || [];
        matches.forEach(m => {
          const id = m.match(/(\d+)/)[0];
          if (id !== currentPid) result.goodsIds.push(id);
        });
      }

      // 중복 제거
      result.relatedIds = [...new Set(result.relatedIds)];
      result.pairIds = [...new Set(result.pairIds)];
      result.goodsIds = [...new Set(result.goodsIds)];

      return result;
    }, pid);

    console.log('  관련 제품 IDs: ' + data.relatedIds.length + '개 → ' + data.relatedIds.join(', '));
    console.log('  함께 구매 IDs: ' + data.pairIds.length + '개 → ' + data.pairIds.join(', '));
    console.log('  goods IDs: ' + data.goodsIds.length + '개 → ' + data.goodsIds.slice(0, 10).join(', '));
    if (data.relationSample) {
      console.log('\n  [relationGoodsData sample]');
      console.log('  ' + data.relationSample.slice(0, 400));
    }
  }

  await browser.close();
}

main().catch(e => console.error(e.message));
