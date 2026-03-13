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

  // 세션 워밍업
  console.log('1. 세션 워밍업...');
  const r1 = await p.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  console.log('   메인: ' + r1.status());
  await new Promise(r => setTimeout(r, 5000));

  // 쿠키 확인
  const cookies = await c.cookies();
  console.log('   쿠키: ' + cookies.length + '개');
  cookies.forEach(c => console.log('     ' + c.name + '=' + c.value.slice(0, 20)));

  // 상세 페이지 접근 (이전에 작동했던 ID)
  console.log('\n2. 상세 페이지 테스트 (2113285)...');
  const r2 = await p.goto('https://www.hwahae.co.kr/products/2113285', { waitUntil: 'networkidle', timeout: 30000 });
  console.log('   status: ' + r2.status());
  await new Promise(r => setTimeout(r, 5000));

  const info = await p.evaluate(() => {
    return {
      title: document.title,
      bodyLen: document.body.innerText.length,
      hasNextData: !!document.getElementById('__NEXT_DATA__'),
      url: location.href,
    };
  });
  console.log('   ' + JSON.stringify(info));

  if (info.hasNextData) {
    const detail = await p.evaluate(() => {
      const el = document.getElementById('__NEXT_DATA__');
      const d = JSON.parse(el.textContent);
      const props = d.props.pageProps || {};
      return {
        keys: Object.keys(props).slice(0, 5),
        hasIngredients: !!props.productIngredientInfoData,
        ingCount: props.productIngredientInfoData?.ingredients?.length || 0,
      };
    });
    console.log('   detail: ' + JSON.stringify(detail));
  }

  // 랭킹 제품으로 테스트
  console.log('\n3. 랭킹 제품 테스트 (2162260)...');
  await new Promise(r => setTimeout(r, 3000));
  const r3 = await p.goto('https://www.hwahae.co.kr/products/2162260', { waitUntil: 'networkidle', timeout: 30000 });
  console.log('   status: ' + r3.status());
  await new Promise(r => setTimeout(r, 5000));

  const info2 = await p.evaluate(() => {
    return {
      title: document.title,
      bodyLen: document.body.innerText.length,
      hasNextData: !!document.getElementById('__NEXT_DATA__'),
      url: location.href,
    };
  });
  console.log('   ' + JSON.stringify(info2));

  await b.close();
}
main().catch(e => console.error(e.message));
