/**
 * 화해 배치 크롤러 — 다중 키워드 순회로 전체 제품 수집
 *
 * 사용법:
 *   node src/crawlers/hwahae-batch.mjs              # 전체 키워드 (기본 20개씩)
 *   node src/crawlers/hwahae-batch.mjs --max 10     # 키워드당 최대 10개
 *   node src/crawlers/hwahae-batch.mjs --save-db    # 크롤링 후 자동 DB 저장
 *   node src/crawlers/hwahae-batch.mjs --keywords "로션,토너"  # 특정 키워드만
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import https from 'https';
import http from 'http';
import { execSync } from 'child_process';

// ── 화장품 카테고리 키워드 (화해 기준) ──
const ALL_KEYWORDS = [
  // 스킨케어
  '토너', '스킨', '로션', '에멀전', '세럼', '에센스', '앰플',
  '크림', '수분크림', '아이크림', '나이트크림',
  '선크림', '선스크린', 'SPF', '자외선차단',
  '미스트', '오일', '페이스오일',
  // 클렌징
  '클렌징폼', '클렌징오일', '클렌징워터', '클렌징밀크', '클렌징밤',
  '폼클렌저', '젤클렌저', '필링', '스크럽', '각질제거',
  // 마스크/팩
  '마스크팩', '시트마스크', '수면팩', '워시오프팩', '클레이마스크',
  // 메이크업
  '파운데이션', '쿠션', 'BB크림', 'CC크림', '프라이머',
  '컨실러', '파우더', '블러셔', '하이라이터', '쉐딩',
  '립스틱', '립틴트', '립글로스', '립밤',
  '아이섀도', '아이라이너', '마스카라', '아이브로우',
  // 바디
  '바디로션', '바디워시', '바디오일', '바디크림',
  '핸드크림', '풋크림', '데오드란트',
  // 헤어
  '샴푸', '컨디셔너', '트리트먼트', '헤어오일', '헤어에센스',
  '두피케어', '탈모샴푸',
  // 남성
  '남성스킨', '남성로션', '쉐이빙', '애프터쉐이브',
  // 성분/기능 키워드
  '레티놀', '비타민C', '나이아신아마이드', '히알루론산', 'PDRN',
  'CICA', '시카', '콜라겐', 'AHA', 'BHA', 'PHA',
  '센텔라', '티트리', '프로폴리스', '스쿠알란',
  // 피부타입
  '민감성', '건성', '지성', '복합성', '트러블',
  '미백', '주름', '탄력', '모공', '여드름',
];

// ── 설정 ──
const BASE_DIR = '/home/kpros/cosmetics-crawler';
const CONFIG = {
  headless: true,
  delay: { min: 2000, max: 5000 },
  keywordDelay: { min: 5000, max: 10000 },
  imageDir: BASE_DIR + '/output/images',
  outputDir: BASE_DIR + '/output',
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function randomDelay(min, max) {
  min = min || CONFIG.delay.min;
  max = max || CONFIG.delay.max;
  return sleep(min + Math.random() * (max - min));
}

// ── 이미지 다운로드 ──
function downloadImage(url, filepath) {
  return new Promise((resolve) => {
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
        return downloadImage(res.headers.location, filepath).then(resolve);
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
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR',
    viewport: { width: 1440, height: 900 },
  });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
  });
  return { browser, context };
}

// ── 세션 사전 획득 ──
async function warmupSession(page) {
  console.log('  세션 획득 중...');
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(3000);
  console.log('  세션 획득 완료');
}

// ── 검색 ──
async function searchProducts(page, keyword, maxCount) {
  const apiResponses = [];
  const handler = async (response) => {
    const url = response.url();
    if ((url.includes('/api/') || url.includes('search') || url.includes('products')) &&
        response.status() === 200 &&
        (response.headers()['content-type'] || '').includes('json')) {
      try { apiResponses.push({ url, body: await response.json() }); } catch (e) {}
    }
  };
  page.on('response', handler);

  const searchUrl = 'https://www.hwahae.co.kr/search?query=' + encodeURIComponent(keyword);
  await page.goto(searchUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(3000);

  for (let i = 0; i < 3; i++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(2000);
  }

  // API 인터셉트
  let products = [];
  for (const resp of apiResponses) {
    const data = resp.body;
    if (Array.isArray(data) && data.length > 0 && data[0].id) {
      for (const p of data.slice(0, maxCount)) products.push(makeProduct(p));
    }
    const list = data?.data?.products || data?.products || data?.data?.items || data?.items || data?.data;
    if (Array.isArray(list) && list.length > 0) {
      for (const p of list.slice(0, maxCount)) products.push(makeProduct(p));
    }
    if (products.length >= maxCount) break;
  }

  // __NEXT_DATA__ goodsTrends
  if (products.length === 0) {
    products = await page.evaluate((max) => {
      const items = [];
      const el = document.getElementById('__NEXT_DATA__');
      if (!el) return items;
      try {
        const data = JSON.parse(el.textContent);
        const props = data.props?.pageProps || {};
        const trends = props.goodsTrends?.data?.trends || [];
        for (const t of trends.slice(0, max)) {
          const prod = t.product || {};
          const brand = t.brand || {};
          items.push({
            hwahae_id: String(prod.id || t.goods_seq || ''),
            name: prod.name || t.name || '',
            brand: brand.full_name || brand.alias || '',
            category: '', price: t.price || prod.price || null,
            thumbnail_url: prod.image_url || t.image || '',
            rating: prod.review_rating || null,
            review_count: prod.review_count || null,
            hwahae_url: prod.id ? ('https://www.hwahae.co.kr/products/' + prod.id) : '',
            source_type: 'trends',
          });
        }
        const picks = props.goodsTrends?.data?.md_picks || [];
        for (const t of picks.slice(0, max - items.length)) {
          const prod = t.product || {};
          const brand = t.brand || {};
          if (!items.find(i => i.hwahae_id === String(prod.id))) {
            items.push({
              hwahae_id: String(prod.id || t.goods_seq || ''),
              name: prod.name || t.name || '',
              brand: brand.full_name || brand.alias || '',
              category: '', price: t.price || prod.price || null,
              thumbnail_url: prod.image_url || t.image || '',
              rating: prod.review_rating || null,
              review_count: prod.review_count || null,
              hwahae_url: prod.id ? ('https://www.hwahae.co.kr/products/' + prod.id) : '',
              source_type: 'md_picks',
            });
          }
        }
      } catch (e) {}
      return items;
    }, maxCount);
  }

  // DOM 추출
  if (products.length === 0) {
    products = await page.evaluate((max) => {
      const items = [];
      const links = document.querySelectorAll('a[href*="/products/"]');
      const seen = new Set();
      links.forEach((link) => {
        if (items.length >= max) return;
        const href = link.href || '';
        const m = href.match(/products\/([\d]+)/);
        if (!m || seen.has(m[1])) return;
        seen.add(m[1]);
        const img = link.querySelector('img');
        items.push({
          hwahae_id: m[1], name: (link.textContent?.trim() || '').slice(0, 100),
          brand: '', category: '', price: null,
          thumbnail_url: img?.src || '', rating: null, review_count: null,
          hwahae_url: 'https://www.hwahae.co.kr/products/' + m[1],
          source_type: 'dom',
        });
      });
      return items;
    }, maxCount);
  }

  page.removeListener('response', handler);
  return products.slice(0, maxCount);
}

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

// ── 상세 페이지 → 전성분 ──
async function getProductDetail(page, product) {
  const url = product.hwahae_url;
  if (!url) return product;
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);
    const detail = await page.evaluate(() => {
      const result = { ingredients: [] };
      const el = document.getElementById('__NEXT_DATA__');
      if (!el) return result;
      try {
        const data = JSON.parse(el.textContent);
        const props = data.props?.pageProps || {};
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
      } catch (e) {}
      return result;
    });
    return { ...product, ingredients: detail.ingredients };
  } catch (e) {
    return product;
  }
}

// ── DB 저장 (save-to-db.mjs 로직 인라인) ──
function saveToDb(products) {
  const PGPASS = '/tmp/pgpass';
  const PSQL = 'PGPASSFILE=' + PGPASS + ' psql -h 127.0.0.1 -U coching_user -d coching_db -t -A';
  execSync("printf '127.0.0.1:5432:coching_db:coching_user:coching2026!' > " + PGPASS + " && chmod 600 " + PGPASS);

  function esc(s) { return (s || '').replace(/'/g, "''"); }
  function runSQL(sql) {
    return execSync(PSQL + " -c \"" + sql.replace(/"/g, '\\"').replace(/\n/g, ' ') + "\"", { encoding: 'utf-8' }).trim();
  }

  let inserted = 0, updated = 0, skipped = 0, ingsSaved = 0;

  for (const p of products) {
    const brandName = esc(p.brand).slice(0, 255);
    const productName = esc(p.name).slice(0, 500);
    const imageUrl = esc(p.thumbnail_url || '');
    const category = esc(p.category).slice(0, 255);
    const price = p.price ? parseFloat(p.price) : null;
    const hwahaeUrl = esc(p.hwahae_url);

    if (!brandName || !productName) { skipped++; continue; }

    const sql = `INSERT INTO product_master (brand_name, product_name, category, image_url, retail_price_usd, source, data_quality_grade, brand_website) VALUES ('${brandName}', '${productName}', '${category}', '${imageUrl}', ${price || 'NULL'}, 'hwahae', 'B', '${hwahaeUrl}') ON CONFLICT (brand_name, product_name) DO UPDATE SET image_url = EXCLUDED.image_url, category = COALESCE(NULLIF(EXCLUDED.category, ''), product_master.category), retail_price_usd = COALESCE(EXCLUDED.retail_price_usd, product_master.retail_price_usd), brand_website = EXCLUDED.brand_website, updated_at = NOW() RETURNING id, (xmax = 0) AS is_insert;`;

    let productId = null;
    try {
      const result = runSQL(sql);
      const parts = result.split('|');
      productId = parseInt(parts[0]);
      if (parts[1] === 't') inserted++; else updated++;
    } catch (e) { skipped++; continue; }

    const ings = p.ingredients || [];
    if (productId && ings.length > 0) {
      for (const ing of ings) {
        const nameKo = esc(ing.name_ko).slice(0, 255);
        const nameInci = esc(ing.name_inci).slice(0, 255);
        const ewg = ing.ewg_grade != null ? ing.ewg_grade : 'NULL';
        const purpose = esc(ing.purpose).slice(0, 500);
        const order = ing.order || 'NULL';
        if (!nameInci && !nameKo) continue;

        try {
          runSQL(`INSERT INTO product_ingredients (product_id, ingredient_order, ingredient_name_ko, ingredient_name_inci, ewg_grade, purpose) VALUES (${productId}, ${order}, '${nameKo}', '${nameInci}', ${ewg}, '${purpose}') ON CONFLICT (product_id, ingredient_name_inci) DO UPDATE SET ewg_grade = EXCLUDED.ewg_grade, purpose = EXCLUDED.purpose, ingredient_order = EXCLUDED.ingredient_order;`);
          ingsSaved++;
        } catch (e) {}

        if (nameInci && ewg !== 'NULL') {
          try {
            runSQL(`UPDATE ingredient_master SET ewg_score = ${ewg}, purpose = COALESCE(NULLIF('${purpose}', ''), purpose), hwahae_id = ${ing.id || 'NULL'}, updated_at = NOW() WHERE LOWER(inci_name) = LOWER('${nameInci}') AND (ewg_score IS NULL OR ewg_score != ${ewg});`);
          } catch (e) {}
        }
      }
    }
  }
  return { inserted, updated, skipped, ingsSaved };
}

// ── 메인 배치 실행 ──
async function main() {
  // 인자 파싱
  const args = process.argv.slice(2);
  let maxPerKeyword = 20;
  let saveDb = false;
  let keywords = ALL_KEYWORDS;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--max' && args[i+1]) { maxPerKeyword = parseInt(args[i+1]); i++; }
    if (args[i] === '--save-db') saveDb = true;
    if (args[i] === '--keywords' && args[i+1]) { keywords = args[i+1].split(','); i++; }
  }

  console.log('============================================');
  console.log('  화해 배치 크롤러 v1.0');
  console.log('============================================');
  console.log('  키워드: ' + keywords.length + '개');
  console.log('  키워드당 최대: ' + maxPerKeyword + '개');
  console.log('  예상 최대 제품: ' + (keywords.length * maxPerKeyword) + '개');
  console.log('  DB 자동 저장: ' + (saveDb ? 'YES' : 'NO'));
  console.log('  예상 소요: ~' + Math.round(keywords.length * maxPerKeyword * 10 / 60) + '분');
  console.log('============================================\n');

  fs.mkdirSync(CONFIG.imageDir, { recursive: true });
  fs.mkdirSync(CONFIG.outputDir, { recursive: true });

  const { browser, context } = await initBrowser();
  const page = await context.newPage();

  // 중복 제거용 (hwahae_id 기준)
  const seenIds = new Set();
  const allProducts = [];
  let totalIngredients = 0;

  // 진행 로그 파일
  const logFile = path.join(CONFIG.outputDir, 'batch_progress.log');

  try {
    await warmupSession(page);

    for (let ki = 0; ki < keywords.length; ki++) {
      const keyword = keywords[ki];
      const progress = '[' + (ki+1) + '/' + keywords.length + ']';
      console.log('\n' + progress + ' 키워드: "' + keyword + '"');

      try {
        const products = await searchProducts(page, keyword, maxPerKeyword);
        const newProducts = products.filter(p => !seenIds.has(p.hwahae_id));
        console.log('  검색: ' + products.length + '개 (신규: ' + newProducts.length + '개)');

        // 상세 페이지 크롤링
        for (let i = 0; i < newProducts.length; i++) {
          const p = newProducts[i];
          seenIds.add(p.hwahae_id);

          // 전성분 추출
          const detailed = await getProductDetail(page, p);
          const ingCount = (detailed.ingredients || []).length;
          totalIngredients += ingCount;

          // 이미지
          if (detailed.thumbnail_url) {
            const ext = (detailed.thumbnail_url.match(/\.(jpg|jpeg|png|webp|gif)/i) || [])[1] || 'jpg';
            const imgPath = path.join(CONFIG.imageDir, 'hwahae_' + detailed.hwahae_id + '.' + ext);
            const saved = await downloadImage(detailed.thumbnail_url, imgPath);
            if (saved) detailed.image_local = imgPath;
          }

          detailed.search_keyword = keyword;
          allProducts.push(detailed);

          const mark = ingCount > 0 ? '+' : '-';
          console.log('  ' + mark + ' [' + (i+1) + '/' + newProducts.length + '] ' +
            (detailed.brand || '?') + ' - ' + (detailed.name || '?').slice(0, 30) +
            ' (성분:' + ingCount + ')');

          if (i < newProducts.length - 1) await randomDelay();
        }

        // 진행 상황 로그
        const logLine = new Date().toISOString() + ' | ' + progress + ' ' + keyword +
          ' | 신규:' + newProducts.length + ' | 누적:' + allProducts.length +
          ' | 전성분:' + totalIngredients + '\n';
        fs.appendFileSync(logFile, logLine);

        // DB 자동 저장 (키워드마다)
        if (saveDb && newProducts.length > 0) {
          const dbResult = saveToDb(allProducts.slice(-newProducts.length));
          console.log('  DB: +' + dbResult.inserted + ' ~' + dbResult.updated + ' 성분:' + dbResult.ingsSaved);
        }

      } catch (e) {
        console.log('  ERROR: ' + e.message.slice(0, 80));
        fs.appendFileSync(logFile, new Date().toISOString() + ' | ERROR ' + keyword + ': ' + e.message.slice(0, 100) + '\n');
      }

      // 키워드 간 긴 딜레이 (WAF 방지)
      if (ki < keywords.length - 1) {
        await randomDelay(CONFIG.keywordDelay.min, CONFIG.keywordDelay.max);
      }
    }

    // 최종 JSON 저장
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const jsonFile = path.join(CONFIG.outputDir, 'hwahae_batch_' + timestamp + '.json');
    fs.writeFileSync(jsonFile, JSON.stringify(allProducts, null, 2));

    // 최종 요약
    const withIng = allProducts.filter(p => p.ingredients && p.ingredients.length > 0).length;
    const withImg = allProducts.filter(p => p.image_local).length;
    console.log('\n============================================');
    console.log('  배치 크롤링 완료');
    console.log('  키워드: ' + keywords.length + '개 처리');
    console.log('  제품: ' + allProducts.length + '개 (중복 제거됨)');
    console.log('  전성분: ' + withIng + '개 제품');
    console.log('  이미지: ' + withImg + '개');
    console.log('  저장: ' + jsonFile);
    if (!saveDb) {
      console.log('');
      console.log('  DB 저장: node src/save-to-db.mjs ' + jsonFile);
    }
    console.log('============================================');

  } catch (e) {
    console.error('\n배치 에러: ' + e.message);
  } finally {
    await browser.close();
  }
}

main().catch(console.error);
