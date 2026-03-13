import { chromium } from 'playwright';

async function main() {
  const b = await chromium.launch({ headless: true, args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage'] });
  const c = await b.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR', viewport: { width: 1440, height: 900 },
  });
  await c.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
  });
  const p = await c.newPage();
  await p.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  await p.goto('https://www.hwahae.co.kr/products/2162260', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));

  const data = await p.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    const d = JSON.parse(el.textContent);
    const props = d.props.pageProps;

    // goodsProductsData 전체 구조
    const gpd = props.goodsProductsData;
    // goodsProductsCommonData 전체 구조
    const gpc = props.goodsProductsCommonData;

    return {
      gpd_keys: gpd ? Object.keys(gpd) : null,
      gpd_meta: gpd?.meta,
      gpd_data_keys: gpd?.data ? Object.keys(gpd.data) : null,
      gpd_data_sample: gpd?.data ? JSON.stringify(gpd.data).slice(0, 500) : null,
      gpc_keys: gpc ? Object.keys(gpc) : null,
      gpc_sample: gpc ? JSON.stringify(gpc).slice(0, 500) : null,
      // productGoodsPairData에서 common 정보
      pair_common: props.productGoodsPairData?.common ? JSON.stringify(props.productGoodsPairData.common).slice(0, 500) : null,
      pair_product: props.productGoodsPairData?.product ? JSON.stringify(props.productGoodsPairData.product).slice(0, 500) : null,
    };
  });

  console.log('=== goodsProductsData ===');
  console.log('keys:', data.gpd_keys);
  console.log('meta:', JSON.stringify(data.gpd_meta));
  console.log('data_keys:', data.gpd_data_keys);
  console.log('data_sample:', data.gpd_data_sample);

  console.log('\n=== goodsProductsCommonData ===');
  console.log('keys:', data.gpc_keys);
  console.log('sample:', data.gpc_sample);

  console.log('\n=== productGoodsPairData.common ===');
  console.log(data.pair_common);
  console.log('\n=== productGoodsPairData.product ===');
  console.log(data.pair_product);

  await b.close();
}
main().catch(e => console.error(e.message));
