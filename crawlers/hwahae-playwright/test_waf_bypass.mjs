/**
 * WAF 통과 테스트 — headed 브라우저로 화해 상세 페이지 접근
 * WAF 챌린지 통과 후 API 응답 인터셉트로 전성분 수집
 */
import { chromium } from 'playwright';

const PRODUCT_ID = '2113285'; // 아누아 PDRN 세럼
const PRODUCT_URL = 'https://www.hwahae.co.kr/products/' + PRODUCT_ID;

async function main() {
  console.log('=== WAF 통과 테스트 ===');
  console.log('URL: ' + PRODUCT_URL);

  // 실제 브라우저 모드 (headed) — WSL에서는 headless + stealth 설정
  const browser = await chromium.launch({
    headless: true,  // WSL에서는 headless만 가능, 대신 stealth 설정 강화
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--disable-web-security',
      '--disable-features=IsolateOrigins,site-per-process',
    ],
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR',
    viewport: { width: 1440, height: 900 },
    // 실제 브라우저처럼 보이기 위한 설정
    javaScriptEnabled: true,
    hasTouch: false,
    isMobile: false,
    deviceScaleFactor: 1,
  });

  // navigator.webdriver 제거 (봇 탐지 우회)
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    // chrome 객체 위장
    window.chrome = { runtime: {} };
    // permissions 위장
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
      parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
    // plugins 위장
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5],
    });
    // languages 위장
    Object.defineProperty(navigator, 'languages', {
      get: () => ['ko-KR', 'ko', 'en-US', 'en'],
    });
  });

  const page = await context.newPage();

  // API 응답 캡처
  const apiResponses = [];
  page.on('response', async (response) => {
    const url = response.url();
    const status = response.status();
    const ct = response.headers()['content-type'] || '';

    // 모든 hwahae API 응답 로깅
    if (url.includes('hwahae') && ct.includes('json') && status === 200) {
      try {
        const body = await response.json();
        apiResponses.push({ url, body });
        const str = JSON.stringify(body);
        console.log('\n  [API] ' + url.slice(0, 100));
        console.log('  keys: ' + Object.keys(body).join(', ').slice(0, 100));
        if (str.includes('ingredient') || str.includes('성분')) {
          console.log('  *** INGREDIENTS FOUND ***');
        }
      } catch (e) {}
    }

    // WAF 관련 응답 로깅
    if (url.includes('awswaf') || url.includes('token')) {
      console.log('  [WAF] ' + status + ' ' + url.slice(0, 80));
    }
  });

  // 1단계: 먼저 메인 페이지로 접속 (쿠키/세션 획득)
  console.log('\n1. 메인 페이지 접속 (세션 획득)...');
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));

  // 쿠키 확인
  const cookies = await context.cookies();
  const wafCookies = cookies.filter(c => c.name.includes('aws') || c.name.includes('waf') || c.name.includes('challenge'));
  console.log('  쿠키: ' + cookies.length + '개 (WAF 관련: ' + wafCookies.length + '개)');
  wafCookies.forEach(c => console.log('    ' + c.name + '=' + c.value.slice(0, 30) + '...'));

  // 2단계: 제품 상세 페이지 접속
  console.log('\n2. 제품 상세 페이지 접속...');
  await page.goto(PRODUCT_URL, { waitUntil: 'networkidle', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));

  // 페이지 상태 확인
  const title = await page.title();
  const bodyLen = await page.evaluate(() => document.body.innerText.length);
  console.log('  title: ' + title);
  console.log('  body length: ' + bodyLen);

  // 전성분 텍스트 확인
  const ingCheck = await page.evaluate(() => {
    const text = document.body.innerText;
    const idx = text.indexOf('전성분');
    if (idx >= 0) return text.slice(idx, idx + 200);
    const idx2 = text.indexOf('성분');
    if (idx2 >= 0) return text.slice(idx2, idx2 + 200);
    return 'NOT FOUND (body len=' + text.length + ')';
  });
  console.log('\n  전성분 텍스트: ' + ingCheck);

  // __NEXT_DATA__ 확인
  const nextData = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    try {
      const data = JSON.parse(el.textContent);
      const props = data.props?.pageProps || {};
      return {
        keys: Object.keys(props),
        hasProduct: !!props.product,
        hasIngredients: !!(props.product?.ingredients || props.ingredients),
      };
    } catch (e) { return { error: e.message }; }
  });
  console.log('\n  __NEXT_DATA__ pageProps: ' + JSON.stringify(nextData));

  // 전성분 탭 클릭 시도
  console.log('\n3. 전성분 탭 클릭 시도...');
  const tabResult = await page.evaluate(() => {
    const elements = document.querySelectorAll('button, a, span, div, li, nav *');
    for (const el of elements) {
      const text = (el.textContent || '').trim();
      if (text === '전성분' || text === '성분' || (text.includes('전성분') && text.length < 20)) {
        el.click();
        return 'clicked: "' + text + '"';
      }
    }
    return 'no tab found';
  });
  console.log('  ' + tabResult);
  await new Promise(r => setTimeout(r, 3000));

  // 클릭 후 전성분 확인
  const ingAfterClick = await page.evaluate(() => {
    const text = document.body.innerText;
    const idx = text.indexOf('전성분');
    if (idx >= 0) return text.slice(idx, idx + 500);
    return 'still not found';
  });
  console.log('  클릭 후: ' + ingAfterClick.slice(0, 300));

  console.log('\n=== API 응답 요약 (' + apiResponses.length + '개) ===');
  for (const r of apiResponses) {
    const s = JSON.stringify(r.body).slice(0, 150);
    console.log('  ' + r.url.slice(0, 80));
    console.log('    ' + s);
  }

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
