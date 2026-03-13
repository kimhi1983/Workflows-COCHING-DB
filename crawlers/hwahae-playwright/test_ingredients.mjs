/**
 * 전성분 데이터 추출 테스트
 * productIngredientInfoData 구조 확인
 */
import { chromium } from 'playwright';

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR',
    viewport: { width: 1440, height: 900 },
  });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
  });

  const page = await context.newPage();

  // 1. 메인 페이지로 세션 획득
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  // 2. 제품 상세 페이지
  await page.goto('https://www.hwahae.co.kr/products/2113285', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));

  // 3. __NEXT_DATA__ 전체 구조 확인
  const result = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return { error: 'no __NEXT_DATA__' };
    const data = JSON.parse(el.textContent);
    const props = data.props?.pageProps || {};

    const output = {};

    // productIngredientInfoData 추출
    if (props.productIngredientInfoData) {
      const ing = props.productIngredientInfoData;
      output.ingredientInfo = {
        keys: Object.keys(ing),
        meta: ing.meta,
        dataKeys: ing.data ? Object.keys(ing.data) : null,
        sample: JSON.stringify(ing).slice(0, 2000),
      };
    }

    // goodsProductsData 추출 (제품 정보)
    if (props.goodsProductsData) {
      const gp = props.goodsProductsData;
      output.goodsProducts = {
        keys: Object.keys(gp),
        dataKeys: gp.data ? Object.keys(gp.data) : null,
      };
    }

    // goodsProductsCommonData
    if (props.goodsProductsCommonData) {
      const gc = props.goodsProductsCommonData;
      output.goodsProductsCommon = {
        keys: Object.keys(gc),
        sample: JSON.stringify(gc).slice(0, 1000),
      };
    }

    return output;
  });

  console.log('=== productIngredientInfoData ===');
  if (result.ingredientInfo) {
    console.log('keys:', result.ingredientInfo.keys);
    console.log('meta:', JSON.stringify(result.ingredientInfo.meta));
    console.log('dataKeys:', result.ingredientInfo.dataKeys);
    console.log('sample:', result.ingredientInfo.sample);
  } else {
    console.log('NOT FOUND');
  }

  console.log('\n=== goodsProductsData ===');
  if (result.goodsProducts) {
    console.log('keys:', result.goodsProducts.keys);
    console.log('dataKeys:', result.goodsProducts.dataKeys);
  }

  console.log('\n=== goodsProductsCommonData ===');
  if (result.goodsProductsCommon) {
    console.log(result.goodsProductsCommon.sample);
  }

  await browser.close();
}

main().catch(e => console.error(e.message));
