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

// ── 브라우저 초기화 ──
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
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    locale: 'ko-KR',
    viewport: { width: 1280, height: 800 },
  });
  return { browser, context };
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

// ── 제품 상세 페이지 스크래핑 (API 인터셉트 포함) ──
async function getProductDetail(page, product) {
  const url = product.hwahae_url;
  if (!url) return product;

  console.log('\n' + String.fromCodePoint(0x1F4CB) + ' 상세: ' + (product.brand || '?') + ' - ' + (product.name || product.hwahae_id));

  try {
    // API 응답 캡처 (전성분 등 클라이언트 API)
    const detailApis = [];
    const apiHandler = async (response) => {
      const rurl = response.url();
      if (response.status() === 200 &&
          (rurl.includes('ingredient') || rurl.includes('product') || rurl.includes('/api/')) &&
          (response.headers()['content-type'] || '').includes('json')) {
        try {
          const body = await response.json();
          detailApis.push({ url: rurl, body });
        } catch (e) { /* not json */ }
      }
    };
    page.on('response', apiHandler);

    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);

    // 전성분 탭/섹션 클릭 시도 (화해는 전성분을 숨겨둘 수 있음)
    try {
      const ingTab = await page.$('[class*="ingredient"], [class*="Ingredient"], [data-tab*="ingredient"], button:has-text("전성분"), a:has-text("전성분"), span:has-text("전성분")');
      if (ingTab) {
        await ingTab.click();
        await sleep(2000);
      }
    } catch (e) { /* 탭이 없을 수 있음 */ }

    // API 인터셉트에서 전성분 추출
    let ingredients = [];
    for (const resp of detailApis) {
      const data = resp.body;
      // ingredients 직접 배열
      const ingList = data?.ingredients || data?.data?.ingredients ||
                      data?.ingredientList || data?.data?.ingredientList ||
                      data?.fullIngredients || data?.data?.fullIngredients;
      if (Array.isArray(ingList) && ingList.length > 0) {
        ingredients = ingList.map((ing, idx) => ({
          name_ko: typeof ing === 'string' ? ing : (ing.name || ing.korean_name || ing.koreanName || ing.nameKo || ''),
          name_inci: typeof ing === 'string' ? '' : (ing.inci_name || ing.inciName || ing.inci || ing.englishName || ''),
          ewg_grade: typeof ing === 'string' ? null : (ing.ewg_grade || ing.ewgGrade || ing.ewgScore || ing.grade || null),
          ewg_color: typeof ing === 'string' ? '' : (ing.ewg_color || ing.ewgColor || ing.gradeColor || ''),
          order: idx + 1,
        }));
        break;
      }
    }

    // 페이지 DOM/NEXT_DATA에서 추출
    const detail = await page.evaluate(() => {
      const result = { ingredients: [], images: [] };

      const nextScript = document.getElementById('__NEXT_DATA__');
      if (nextScript) {
        try {
          const data = JSON.parse(nextScript.textContent);
          const props = data.props?.pageProps || {};
          const p = props.product || props.detail || props.data || props;

          result.name = p.title || p.name || p.productName || '';
          result.brand = p.brand || p.brandName || '';
          result.category = p.category || p.categoryName || '';
          result.price = p.price || p.salePrice || null;
          result.full_image_url = p.imageUrl || p.image || '';
          result.rating = p.rating || p.averageRating || null;
          result.review_count = p.reviewCount || null;
          result.description = p.description || '';

          if (Array.isArray(p.images)) result.images = p.images;
          if (Array.isArray(p.imageList)) result.images = p.imageList;

          // 전성분
          const ings = p.ingredients || p.ingredientList || p.fullIngredients || [];
          if (Array.isArray(ings) && ings.length > 0) {
            result.ingredients = ings.map((ing, idx) => ({
              name_ko: typeof ing === 'string' ? ing : (ing.name || ing.koreanName || ing.nameKo || ''),
              name_inci: typeof ing === 'string' ? '' : (ing.inciName || ing.inci || ing.englishName || ''),
              ewg_grade: typeof ing === 'string' ? null : (ing.ewgGrade || ing.ewgScore || null),
              ewg_color: typeof ing === 'string' ? '' : (ing.ewgColor || ing.gradeColor || ''),
              order: idx + 1,
            }));
          }
        } catch (e) { /* ignore */ }
      }

      // DOM 보완: 이미지
      if (!result.full_image_url) {
        const ogImg = document.querySelector('meta[property="og:image"]');
        if (ogImg) result.full_image_url = ogImg.content;
      }

      // DOM 보완: 이름
      if (!result.name) {
        const ogTitle = document.querySelector('meta[property="og:title"]');
        if (ogTitle) result.name = ogTitle.content;
      }

      // DOM 보완: 전성분
      if (result.ingredients.length === 0) {
        // 전성분 텍스트가 한 덩어리로 있을 수 있음
        const allText = document.body.innerText || '';
        const ingMatch = allText.match(/전성분[:\s]*([\s\S]{20,2000}?)(?=\n\n|\n[가-힣]+\s|$)/);
        if (ingMatch) {
          const raw = ingMatch[1].trim();
          const parts = raw.split(/[,，]/).map(s => s.trim()).filter(s => s.length > 0 && s.length < 100);
          if (parts.length >= 3) {
            result.ingredients = parts.map((name, idx) => ({
              name_ko: name,
              name_inci: '',
              ewg_grade: null,
              ewg_color: '',
              order: idx + 1,
            }));
          }
        }
      }

      return result;
    });

    // API 인터셉트 해제
    page.removeListener('response', apiHandler);

    // 전성분: API > NEXT_DATA > DOM 우선순위
    const finalIngredients = ingredients.length > 0 ? ingredients :
                             detail.ingredients.length > 0 ? detail.ingredients : [];

    // 병합 (검색에서 가져온 원래 이름 우선, OG title은 긴 홍보문구 포함)
    const detailName = detail.name || '';
    const useName = (product.name && product.name.length < 100) ? product.name :
                    (detailName.length < 100 ? detailName : product.name);

    return {
      ...product,
      name: useName,
      brand: detail.brand || product.brand,
      category: detail.category || product.category,
      price: detail.price || product.price,
      full_image_url: detail.full_image_url || product.thumbnail_url,
      images: detail.images || [],
      rating: detail.rating || product.rating,
      review_count: detail.review_count || product.review_count,
      description: detail.description || '',
      ingredients: finalIngredients,
    };
  } catch (e) {
    console.log('   ' + String.fromCodePoint(0x274C) + ' 에러: ' + e.message);
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
    // 1단계: 검색
    const products = await searchProducts(page, keyword, maxCount);

    if (products.length === 0) {
      console.log('\n' + String.fromCodePoint(0x26A0) + ' 검색 결과가 없습니다.');
      console.log('   화해는 SPA로 렌더링하므로 페이지 구조가 변경되었을 수 있습니다.');

      // 디버깅: 스크린샷 + HTML 저장
      await page.screenshot({ path: path.join(CONFIG.outputDir, 'debug_search.png'), fullPage: true });
      const html = await page.content();
      fs.writeFileSync(path.join(CONFIG.outputDir, 'debug_search.html'), html);
      console.log('   디버그 스크린샷/HTML 저장 완료');

      await browser.close();
      return;
    }

    // 2단계: 이미지 다운로드 (상세 페이지는 WAF 차단으로 스킵)
    const detailed = [];
    for (let i = 0; i < products.length; i++) {
      const product = products[i];

      // 이미지 다운로드 (검색에서 얻은 thumbnail_url 사용)
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
      const hasImg = product.thumbnail_url ? String.fromCodePoint(0x2705) : String.fromCodePoint(0x274C);
      console.log('   [' + (i+1) + '/' + products.length + '] ' + (product.brand||'?') + ' - ' + (product.name||'?') + ' ' + hasImg);
    }

    // 결과 저장
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const jsonFile = path.join(CONFIG.outputDir, 'hwahae_' + keyword + '_' + timestamp + '.json');
    fs.writeFileSync(jsonFile, JSON.stringify(detailed, null, 2));

    // 요약
    console.log('\n============================================');
    console.log('  수집 완료: ' + detailed.length + '개 제품');
    console.log('  이미지: ' + detailed.filter(p => p.image_local).length + '개 다운로드');
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
