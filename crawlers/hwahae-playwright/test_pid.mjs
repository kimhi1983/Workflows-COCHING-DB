import { chromium } from 'playwright';

async function main() {
  const b = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const c = await b.newContext({ userAgent: 'Mozilla/5.0 Chrome/131.0.0.0', locale: 'ko-KR' });
  await c.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
  });
  const p = await c.newPage();

  await p.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  await p.goto('https://www.hwahae.co.kr/rankings', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  const data = await p.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    const d = JSON.parse(el.textContent);
    const products = d.props.pageProps.rankingProducts.data.details;
    return products.slice(0, 3).map(p => ({
      product_id: p.goods.product_id,
      goods_id: p.goods.id,
      name: (p.goods.name || '').slice(0, 40),
    }));
  });
  console.log('Rankings products:');
  console.log(JSON.stringify(data, null, 2));

  // 테스트: product_id로 접근
  const pid = data[0].product_id;
  console.log('\nAccessing /products/' + pid);
  await p.goto('https://www.hwahae.co.kr/products/' + pid, { waitUntil: 'networkidle', timeout: 20000 });
  await new Promise(r => setTimeout(r, 3000));
  const r1 = await p.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return 'no __NEXT_DATA__';
    const d = JSON.parse(el.textContent);
    const props = d.props.pageProps || {};
    return {
      keys: Object.keys(props),
      statusCode: props.statusCode || null,
      hasGoods: !!props.goodsProductsData,
      hasIngredients: !!props.productIngredientInfoData,
    };
  });
  console.log('Result: ' + JSON.stringify(r1));

  // 테스트: goods_id로 접근
  const gid = data[0].goods_id;
  console.log('\nAccessing /products/' + gid);
  await p.goto('https://www.hwahae.co.kr/products/' + gid, { waitUntil: 'networkidle', timeout: 20000 });
  await new Promise(r => setTimeout(r, 3000));
  const r2 = await p.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return 'no __NEXT_DATA__';
    const d = JSON.parse(el.textContent);
    const props = d.props.pageProps || {};
    return {
      keys: Object.keys(props),
      statusCode: props.statusCode || null,
      hasGoods: !!props.goodsProductsData,
      hasIngredients: !!props.productIngredientInfoData,
    };
  });
  console.log('Result: ' + JSON.stringify(r2));

  await b.close();
}
main().catch(e => console.error(e.message));
