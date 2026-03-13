/**
 * 화해(Hwahae) Playwright 크롤러
 * 제품 검색 → 상세 페이지 → 이미지 + 전성분 수집
 *
 * 사용법: node src/crawlers/hwahae.mjs <키워드> [최대개수]
 * 예시:  node src/crawlers/hwahae.mjs 선크림 5
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import https from 'https';
import http from 'http';

// ── 설정 ──
const BASE_DIR = '/home/kpros/cosmetics-crawler';
const CONFIG = {
  headless: true,
  delay: { min: 2000, max: 4000 },
  maxRetries: 3,
  imageDir: BASE_DIR + '/output/images',
  outputDir: BASE_DIR + '/output',
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function randomDelay() {
  const ms = CONFIG.delay.min + Math.random() * (CONFIG.delay.max - CONFIG.delay.min);
  return sleep(ms);
}

// ── 이미지 다운로드 ──
function downloadImage(url, filepath) {
  return new Promise((resolve, reject) => {
    if (!url || !url.startsWith('http')) return resolve(null);
    const mod = url.startsWith('https') ? https : http;
    const file = fs.createWriteStream(filepath);
    mod.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0' },
      timeout: 15000
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        file.close();
        if (fs.existsSync(filepath)) fs.unlinkSync(filepath);
        return downloadImage(res.headers.location, filepath).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) {
        file.close();
        if (fs.existsSync(filepath)) fs.unlinkSync(filepath);
        return resolve(null);
      }
      res.pipe(file);
      file.on('finish', () => { file.close(); resolve(filepath); });
    }).on('error', () => {
      file.close();
      if (fs.existsSync(filepath)) fs.unlinkSync(filepath);
      resolve(null);
    });
  });
}

// ── 브라우저 초기화 (stealth + WAF 통과) ──
async function initBrowser() {
  const browser = await chromium.launch({
    headless: CONFIG.headless,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-dev-shm-usage',
    ],
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR',
    viewport: { width: 1440, height: 900 },
  });
  // 봇 탐지 우회 (navigator.webdriver 제거 등)
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
  });
  return { browser, context };
}

// ── 세션 사전 획득 (WAF 토큰 + 쿠키) ──
async function warmupSession(page) {
  console.log('  세션 획득 중 (메인 페이지)...');
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(3000);
  console.log('  세션 획득 완료');
}

// ── 화해 검색 → 제품 목록 수집 (API 인터셉트 + __NEXT_DATA__ + DOM) ──
async function searchProducts(page, keyword, maxCount) {
  console.log('\n' + String.fromCodePoint(0x1F50D) + ' 화해 검색: "' + keyword + '" (최대 ' + maxCount + '개)');

  // API 응답 가로채기
  const apiResponses = [];
  page.on('response', async (response) => {
    const url = response.url();
    // 화해 내부 API 응답 캡처 (검색, 제품 목록 등)
    if ((url.includes('/api/') || url.includes('search') || url.includes('products')) &&
        response.status() === 200 &&
        (response.headers()['content-type'] || '').includes('json')) {
      try {
        const body = await response.json();
        apiResponses.push({ url, body });
      } catch (e) { /* not json */ }
    }
  });

  const searchUrl = 'https://www.hwahae.co.kr/search?query=' + encodeURIComponent(keyword);
  await page.goto(searchUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(3000);

  // 스크롤하여 더 많은 API 호출 유도
  for (let i = 0; i < 3; i++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(2000);
  }

  // === 방법 1: API 인터셉트에서 제품 추출 ===
  let products = [];
  for (const resp of apiResponses) {
    const data = resp.body;
    // 배열 형태 응답
    if (Array.isArray(data) && data.length > 0 && data[0].id) {
      for (const p of data.slice(0, maxCount)) {
        products.push(makeProduct(p));
      }
    }
    // { data: [...] } 또는 { products: [...] } 형태
    const list = data?.data?.products || data?.products || data?.data?.items || data?.items || data?.data;
    if (Array.isArray(list) && list.length > 0) {
      for (const p of list.slice(0, maxCount)) {
        products.push(makeProduct(p));
      }
    }
    if (products.length >= maxCount) break;
  }

  // === 방법 2: __NEXT_DATA__ goodsTrends (트렌드/인기 제품) ===
  if (products.length === 0) {
    products = await page.evaluate((max) => {
      const items = [];
      const nextScript = document.getElementById('__NEXT_DATA__');
      if (!nextScript) return items;

      try {
        const data = JSON.parse(nextScript.textContent);
        const props = data.props?.pageProps || {};

        // goodsTrends 구조 (화해 검색 페이지)
        const trends = props.goodsTrends?.data?.trends || [];
        for (const t of trends.slice(0, max)) {
          const prod = t.product || {};
          const brand = t.brand || {};
          items.push({
            hwahae_id: String(prod.id || t.goods_seq || ''),
            name: prod.name || t.name || '',
            brand: brand.full_name || brand.alias || '',
            category: '',
            price: t.price || prod.price || null,
            thumbnail_url: prod.image_url || t.image || '',
            rating: prod.review_rating || null,
            review_count: prod.review_count || null,
            hwahae_url: prod.id ? ('https://www.hwahae.co.kr/products/' + prod.id) : '',
            source_type: 'trends',
          });
        }

        // md_picks 구조
        const picks = props.goodsTrends?.data?.md_picks || [];
        for (const t of picks.slice(0, max - items.length)) {
          const prod = t.product || {};
          const brand = t.brand || {};
          if (!items.find(i => i.hwahae_id === String(prod.id))) {
            items.push({
              hwahae_id: String(prod.id || t.goods_seq || ''),
              name: prod.name || t.name || '',
              brand: brand.full_name || brand.alias || '',
              category: '',
              price: t.price || prod.price || null,
              thumbnail_url: prod.image_url || t.image || '',
              rating: prod.review_rating || null,
              review_count: prod.review_count || null,
              hwahae_url: prod.id ? ('https://www.hwahae.co.kr/products/' + prod.id) : '',
              source_type: 'md_picks',
            });
          }
        }

        // 일반적인 products/items 구조도 탐색
        const lists = [
          props.products, props.items, props.searchResult?.products,
          props.data?.products,
        ].filter(Boolean);
        for (const list of lists) {
          if (Array.isArray(list) && list.length > 0 && items.length < max) {
            for (const p of list.slice(0, max - items.length)) {
              items.push({
                hwahae_id: String(p.id || p.productId || ''),
                name: p.title || p.name || p.productName || '',
                brand: p.brand || p.brandName || '',
                category: p.category || p.categoryName || '',
                price: p.price || p.salePrice || null,
                thumbnail_url: p.imageUrl || p.thumbnailImage || p.image || '',
                rating: p.rating || p.averageRating || null,
                review_count: p.reviewCount || null,
                hwahae_url: p.id ? ('https://www.hwahae.co.kr/products/' + p.id) : '',
                source_type: 'next_data',
              });
            }
            break;
          }
        }
      } catch (e) { /* ignore */ }

      return items;
    }, maxCount);
  }

  // === 방법 3: DOM에서 직접 추출 ===
  if (products.length === 0) {
    products = await page.evaluate((max) => {
      const items = [];
      const links = document.querySelectorAll('a[href*="/products/"]');
      const seen = new Set();
      links.forEach((link) => {
        if (items.length >= max) return;
        const href = link.href || '';
        const idMatch = href.match(/products\/([\d]+)/);
        if (!idMatch || seen.has(idMatch[1])) return;
        seen.add(idMatch[1]);

        const img = link.querySelector('img');
        const text = link.textContent?.trim() || '';
        items.push({
          hwahae_id: idMatch[1],
          name: text.slice(0, 100),
          brand: '',
          category: '',
          price: null,
          thumbnail_url: img?.src || '',
          rating: null,
          review_count: null,
          hwahae_url: 'https://www.hwahae.co.kr/products/' + idMatch[1],
          source_type: 'dom',
        });
      });
      return items;
    }, maxCount);
  }

  products = products.slice(0, maxCount);
  console.log('   ' + String.fromCodePoint(0x1F4E6) + ' 검색 결과: ' + products.length + '개 제품');
  return products;
}

// 제품 객체 정규화 헬퍼
function makeProduct(p) {
  const prod = p.product || {};
  const brand = p.brand || {};
  return {
    hwahae_id: String(prod.id || p.id || p.productId || ''),
    name: prod.name || p.title || p.name || p.productName || '',
    brand: brand.full_name || brand.alias || p.brand || p.brandName || '',
    category: p.category || p.categoryName || '',
    price: p.price || prod.price || p.salePrice || null,
    thumbnail_url: prod.image_url || p.imageUrl || p.thumbnailImage || p.image || '',
    rating: prod.review_rating || p.rating || p.averageRating || null,
    review_count: prod.review_count || p.reviewCount || null,
    hwahae_url: (prod.id || p.id) ? ('https://www.hwahae.co.kr/products/' + (prod.id || p.id)) : '',
    source_type: 'api',
  };
}

// ── 제품 상세 페이지 — __NEXT_DATA__.productIngredientInfoData에서 전성분 추출 ──
async function getProductDetail(page, product) {
  const url = product.hwahae_url;
  if (!url) return product;

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);

    const detail = await page.evaluate(() => {
      const result = { ingredients: [] };
      const nextScript = document.getElementById('__NEXT_DATA__');
      if (!nextScript) return result;

      try {
        const data = JSON.parse(nextScript.textContent);
        const props = data.props?.pageProps || {};

        // 화해 전성분 구조: productIngredientInfoData.ingredients[]
        const ingData = props.productIngredientInfoData;
        if (ingData && Array.isArray(ingData.ingredients)) {
          result.ingredients = ingData.ingredients.map((ing, idx) => ({
            id: ing.id || null,
            name_ko: (ing.korean || '').split(',')[0].trim(),
            name_inci: (ing.english || '').split(',')[0].trim(),
            ewg_grade: ing.ewg ? parseInt(ing.ewg) : null,
            ewg_data: ing.ewg_data_availability_text || '',
            is_allergy: ing.is_allergy || false,
            skin_type: ing.skin_type || null,
            purpose: ing.purpose || '',
            limitation: ing.limitation || '',
            forbidden: ing.forbidden || '',
            order: idx + 1,
          }));
        }
      } catch (e) { /* ignore */ }
      return result;
    });

    const ingCount = detail.ingredients.length;
    const mark = ingCount > 0 ? String.fromCodePoint(0x2705) : String.fromCodePoint(0x274C);
    console.log('   ' + mark + ' 전성분: ' + ingCount + '개  (' + (product.brand || '') + ' - ' + (product.name || ''));

    return {
      ...product,
      ingredients: detail.ingredients,
    };
  } catch (e) {
    console.log('   ' + String.fromCodePoint(0x274C) + ' 상세 에러: ' + e.message);
    return product;
  }
}

// ── 메인 실행 ──
async function main() {
  const keyword = process.argv[2] || '선크림';
  const maxCount = parseInt(process.argv[3]) || 5;

  console.log('============================================');
  console.log('  화해(Hwahae) Playwright 크롤러 v1.0');
  console.log('============================================');
  console.log('  키워드: ' + keyword + ', 최대: ' + maxCount + '개');

  fs.mkdirSync(CONFIG.imageDir, { recursive: true });
  fs.mkdirSync(CONFIG.outputDir, { recursive: true });

  const { browser, context } = await initBrowser();
  const page = await context.newPage();

  try {
    // 1단계: 세션 사전 획득 (WAF 토큰 + 쿠키)
    await warmupSession(page);

    // 2단계: 검색
    const products = await searchProducts(page, keyword, maxCount);

    if (products.length === 0) {
      console.log('\n' + String.fromCodePoint(0x26A0) + ' 검색 결과가 없습니다.');
      console.log('   화해는 SPA로 렌더링하므로 페이지 구조가 변경되었을 수 있습니다.');

      await page.screenshot({ path: path.join(CONFIG.outputDir, 'debug_search.png'), fullPage: true });
      const html = await page.content();
      fs.writeFileSync(path.join(CONFIG.outputDir, 'debug_search.html'), html);
      console.log('   디버그 스크린샷/HTML 저장 완료');

      await browser.close();
      return;
    }

    // 3단계: 상세 페이지 → 전성분 추출 + 이미지 다운로드
    console.log('\n' + String.fromCodePoint(0x1F9EA) + ' 상세 페이지 크롤링 (전성분 + 이미지)...');
    const detailed = [];
    for (let i = 0; i < products.length; i++) {
      console.log('\n  [' + (i+1) + '/' + products.length + '] ' + (products[i].brand||'?') + ' - ' + (products[i].name||'?'));

      // 전성분 추출 (상세 페이지)
      let product = await getProductDetail(page, products[i]);

      // 이미지 다운로드
      const imgUrl = product.thumbnail_url;
      if (imgUrl) {
        const ext = (imgUrl.match(/\.(jpg|jpeg|png|webp|gif)/i) || [])[1] || 'jpg';
        const imgPath = path.join(CONFIG.imageDir, 'hwahae_' + product.hwahae_id + '.' + ext);
        const saved = await downloadImage(imgUrl, imgPath);
        if (saved) {
          product.image_local = imgPath;
          console.log('   ' + String.fromCodePoint(0x1F4BE) + ' 이미지: ' + path.basename(imgPath));
        }
      }

      detailed.push(product);

      // WAF 감지 방지를 위한 랜덤 딜레이
      if (i < products.length - 1) {
        await randomDelay();
      }
    }

    // 결과 저장
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const jsonFile = path.join(CONFIG.outputDir, 'hwahae_' + keyword + '_' + timestamp + '.json');
    fs.writeFileSync(jsonFile, JSON.stringify(detailed, null, 2));

    // 요약
    const withIng = detailed.filter(p => p.ingredients && p.ingredients.length > 0).length;
    const withImg = detailed.filter(p => p.image_local).length;
    console.log('\n============================================');
    console.log('  수집 완료: ' + detailed.length + '개 제품');
    console.log('  전성분: ' + withIng + '개 제품 수집');
    console.log('  이미지: ' + withImg + '개 다운로드');
    console.log('  저장: ' + jsonFile);
    console.log('');
    console.log('  DB 저장: node src/save-to-db.mjs ' + jsonFile);
    console.log('============================================');

  } catch (e) {
    console.error('\n크롤링 에러: ' + e.message);
    await page.screenshot({ path: path.join(CONFIG.outputDir, 'error.png'), fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
}

main().catch(console.error);
