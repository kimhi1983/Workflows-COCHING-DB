/**
 * 화해 전체 제품 크롤러 — 시드 확장 + ID 스캔 방식
 *
 * 전략:
 *  1. 랭킹 페이지에서 시드 product_id 수집 (20개)
 *  2. 시드 제품 상세 페이지 크롤링 (전성분 + 이미지)
 *  3. product_id 범위 스캔 (1800000~2200000, 간격 조정)
 *  4. 결과 자동 DB 저장
 *
 * 사용법:
 *   node src/crawlers/hwahae-full.mjs                    # 전체 (시드 + 스캔)
 *   node src/crawlers/hwahae-full.mjs --seed-only         # 시드(랭킹)만
 *   node src/crawlers/hwahae-full.mjs --scan-only          # ID 스캔만
 *   node src/crawlers/hwahae-full.mjs --scan-start 2100000 --scan-end 2110000 --scan-step 100
 *   node src/crawlers/hwahae-full.mjs --max 50            # 최대 50개
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import https from 'https';
import http from 'http';
import { execSync } from 'child_process';

const BASE_DIR = '/home/kpros/cosmetics-crawler';
const CONFIG = {
  headless: true,
  delay: { min: 2000, max: 5000 },
  imageDir: BASE_DIR + '/output/images',
  outputDir: BASE_DIR + '/output',
  // ID 스캔 범위 (화해 product_id 관찰 범위)
  scanStart: 1800000,
  scanEnd: 2200000,
  scanStep: 2000, // 2000 간격으로 샘플링 → ~200개 시도
  maxProducts: 500,
  // 진행 상태 파일
  progressFile: BASE_DIR + '/output/crawl_progress.json',
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function randomDelay() {
  return sleep(CONFIG.delay.min + Math.random() * (CONFIG.delay.max - CONFIG.delay.min));
}

function downloadImage(url, filepath) {
  return new Promise((resolve) => {
    if (!url || !url.startsWith('http')) return resolve(null);
    const mod = url.startsWith('https') ? https : http;
    const file = fs.createWriteStream(filepath);
    mod.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0' },
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

async function initBrowser() {
  const browser = await chromium.launch({
    headless: CONFIG.headless,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'ko-KR', viewport: { width: 1440, height: 900 },
  });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
  });
  return { browser, context };
}

async function warmupSession(page) {
  console.log('  세션 획득 중...');
  await page.goto('https://www.hwahae.co.kr/', { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(3000);
  console.log('  세션 획득 완료');
}

// ── 랭킹 페이지에서 시드 ID 수집 ──
async function getSeedIds(page) {
  console.log('\n[시드] 랭킹 페이지에서 제품 ID 수집...');
  await page.goto('https://www.hwahae.co.kr/rankings', { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(3000);

  const ids = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return [];
    const d = JSON.parse(el.textContent);
    const products = d.props?.pageProps?.rankingProducts?.data?.details || [];
    return products.map(p => p.goods?.product_id).filter(Boolean);
  });

  console.log('  랭킹 시드: ' + ids.length + '개');
  return ids;
}

// ── 제품 상세 페이지 크롤링 ──
async function crawlProduct(page, productId) {
  const url = 'https://www.hwahae.co.kr/products/' + productId;

  try {
    // products/{id} → goods/{gid} 리다이렉트 발생하므로 충분한 대기 필요
    const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    const status = response ? response.status() : 0;
    if (!response || status >= 400) {
      console.log('    [debug] ' + productId + ' status:' + status);
      return null;
    }
    await sleep(4000);

    // __NEXT_DATA__ 대기 (리다이렉트 후 렌더링 시간)
    let hasData = await page.evaluate(() => !!document.getElementById('__NEXT_DATA__'));
    if (!hasData) {
      await sleep(3000);
      hasData = await page.evaluate(() => !!document.getElementById('__NEXT_DATA__'));
      if (!hasData) {
        console.log('    [debug] ' + productId + ' no __NEXT_DATA__');
        return null;
      }
    }

    const data = await page.evaluate((pid) => {
      const el = document.getElementById('__NEXT_DATA__');
      if (!el) return { _debug: 'no_el' };

      try {
        const d = JSON.parse(el.textContent);
        const props = d.props?.pageProps || {};

        // 404 또는 에러 페이지 체크
        if (props.statusCode === 404 || props.type === 'NOT_FOUND') {
          return { _debug: '404', statusCode: props.statusCode, type: props.type };
        }

        // 제품 기본 정보: productGoodsPairData.product + .common
        const pairData = props.productGoodsPairData || {};
        const pairProduct = pairData.product || {};
        const pairCommon = pairData.common || {};
        const pairBrand = pairProduct.brand || {};

        // 가격 추출 (buy_info: "120ml / 22,000원")
        let price = null;
        if (pairProduct.buy_info) {
          const priceMatch = pairProduct.buy_info.match(/([\d,]+)원/);
          if (priceMatch) price = parseInt(priceMatch[1].replace(/,/g, ''));
        }

        const product = {
          hwahae_id: String(pid),
          name: pairProduct.name || '',
          brand: pairBrand.full_name || pairBrand.name || '',
          category: '',
          price: price,
          thumbnail_url: pairProduct.image_url || '',
          rating: pairCommon.avg_ratings || null,
          review_count: pairCommon.review_count || null,
          hwahae_url: location.href,
          source_type: 'detail_crawl',
          ingredients: [],
        };

        // 전성분
        const ingData = props.productIngredientInfoData;
        if (ingData && Array.isArray(ingData.ingredients)) {
          product.ingredients = ingData.ingredients.map((ing, idx) => ({
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

        // 카테고리 (어워드에서 추출)
        const awards = props.productAwardsData || [];
        if (awards.length > 0 && awards[0].category_full_name) {
          product.category = awards[0].category_full_name.split(':').pop() || '';
        }

        // 이름이 없으면 무효
        if (!product.name && !product.brand) return null;

        return product;
      } catch (e) { return null; }
    }, productId);

    return data;
  } catch (e) {
    console.log('    [debug] ' + productId + ' exception: ' + e.message.slice(0, 60));
    return null;
  }
}

// ── DB 저장 ──
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

// ── 진행 상태 저장/로드 ──
function loadProgress() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG.progressFile, 'utf-8'));
  } catch (e) {
    return { scannedIds: [], validIds: [], lastScanId: CONFIG.scanStart, totalCrawled: 0 };
  }
}

function saveProgress(progress) {
  fs.writeFileSync(CONFIG.progressFile, JSON.stringify(progress, null, 2));
}

// ── 메인 ──
async function main() {
  const args = process.argv.slice(2);
  let seedOnly = args.includes('--seed-only');
  let scanOnly = args.includes('--scan-only');
  let maxProducts = CONFIG.maxProducts;
  let scanStart = CONFIG.scanStart;
  let scanEnd = CONFIG.scanEnd;
  let scanStep = CONFIG.scanStep;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--max') maxProducts = parseInt(args[i+1]) || maxProducts;
    if (args[i] === '--scan-start') scanStart = parseInt(args[i+1]) || scanStart;
    if (args[i] === '--scan-end') scanEnd = parseInt(args[i+1]) || scanEnd;
    if (args[i] === '--scan-step') scanStep = parseInt(args[i+1]) || scanStep;
  }

  const progress = loadProgress();

  console.log('============================================');
  console.log('  화해 전체 크롤러 v1.0');
  console.log('============================================');
  console.log('  모드: ' + (seedOnly ? '시드만' : scanOnly ? 'ID스캔만' : '시드+스캔'));
  console.log('  최대: ' + maxProducts + '개');
  if (!seedOnly) {
    console.log('  스캔 범위: ' + scanStart + ' ~ ' + scanEnd + ' (step ' + scanStep + ')');
    console.log('  예상 시도: ' + Math.ceil((scanEnd - scanStart) / scanStep) + '회');
  }
  console.log('  이전 진행: ' + progress.totalCrawled + '개 수집됨');
  console.log('============================================\n');

  fs.mkdirSync(CONFIG.imageDir, { recursive: true });
  fs.mkdirSync(CONFIG.outputDir, { recursive: true });

  const { browser, context } = await initBrowser();
  const page = await context.newPage();

  const crawledIds = new Set(progress.scannedIds || []);
  const allProducts = [];
  let consecutive404 = 0;
  const startTime = Date.now();

  try {
    await warmupSession(page);

    // ── 1단계: 시드 크롤링 ──
    if (!scanOnly) {
      const seedIds = await getSeedIds(page);
      const newSeeds = seedIds.filter(id => !crawledIds.has(String(id)));
      console.log('\n[시드] 신규 ' + newSeeds.length + '개 크롤링...\n');

      for (let i = 0; i < newSeeds.length && allProducts.length < maxProducts; i++) {
        const pid = newSeeds[i];
        crawledIds.add(String(pid));

        const product = await crawlProduct(page, pid);
        if (product) {
          // 이미지 다운로드
          if (product.thumbnail_url) {
            const ext = (product.thumbnail_url.match(/\.(jpg|jpeg|png|webp|gif)/i) || [])[1] || 'jpg';
            const imgPath = path.join(CONFIG.imageDir, 'hwahae_' + pid + '.' + ext);
            const saved = await downloadImage(product.thumbnail_url, imgPath);
            if (saved) product.image_local = imgPath;
          }

          allProducts.push(product);
          const ingCount = product.ingredients.length;
          console.log('  + [' + allProducts.length + '] ' + product.brand + ' - ' + product.name.slice(0, 35) + ' (성분:' + ingCount + ')');
        }
        await randomDelay();
      }

      if (allProducts.length > 0) {
        const dbResult = saveToDb(allProducts);
        console.log('\n  [DB] 시드 저장: +' + dbResult.inserted + ' ~' + dbResult.updated + ' 성분:' + dbResult.ingsSaved);
      }
    }

    // ── 2단계: ID 스캔 ──
    if (!seedOnly && allProducts.length < maxProducts) {
      const resumeId = Math.max(scanStart, progress.lastScanId || scanStart);
      console.log('\n[스캔] ID ' + resumeId + ' ~ ' + scanEnd + ' (step ' + scanStep + ')...\n');

      let scanCount = 0;
      let hitCount = 0;
      let batchProducts = [];

      for (let pid = resumeId; pid <= scanEnd && allProducts.length < maxProducts; pid += scanStep) {
        if (crawledIds.has(String(pid))) continue;
        crawledIds.add(String(pid));
        scanCount++;

        const product = await crawlProduct(page, pid);

        if (product) {
          consecutive404 = 0;
          hitCount++;

          if (product.thumbnail_url) {
            const ext = (product.thumbnail_url.match(/\.(jpg|jpeg|png|webp|gif)/i) || [])[1] || 'jpg';
            const imgPath = path.join(CONFIG.imageDir, 'hwahae_' + pid + '.' + ext);
            const saved = await downloadImage(product.thumbnail_url, imgPath);
            if (saved) product.image_local = imgPath;
          }

          allProducts.push(product);
          batchProducts.push(product);
          console.log('  + [' + allProducts.length + '] ID:' + pid + ' ' + product.brand + ' - ' + product.name.slice(0, 30) + ' (성분:' + product.ingredients.length + ')');

          // 유효 ID 발견 시 주변 탐색 (±100, ±50 간격)
          if (scanStep > 100) {
            const nearbyOffsets = [-500, -200, -100, 100, 200, 500];
            for (const offset of nearbyOffsets) {
              const nearId = pid + offset;
              if (nearId >= scanStart && nearId <= scanEnd && !crawledIds.has(String(nearId)) && allProducts.length < maxProducts) {
                crawledIds.add(String(nearId));
                const nearProduct = await crawlProduct(page, nearId);
                if (nearProduct) {
                  if (nearProduct.thumbnail_url) {
                    const ext = (nearProduct.thumbnail_url.match(/\.(jpg|jpeg|png|webp|gif)/i) || [])[1] || 'jpg';
                    const imgPath = path.join(CONFIG.imageDir, 'hwahae_' + nearId + '.' + ext);
                    const saved = await downloadImage(nearProduct.thumbnail_url, imgPath);
                    if (saved) nearProduct.image_local = imgPath;
                  }
                  allProducts.push(nearProduct);
                  batchProducts.push(nearProduct);
                  console.log('  + [' + allProducts.length + '] ID:' + nearId + ' (near) ' + nearProduct.brand + ' - ' + nearProduct.name.slice(0, 30));
                }
                await sleep(1000);
              }
            }
          }
        } else {
          consecutive404++;
          if (scanCount % 10 === 0) {
            process.stdout.write('  . scan ' + pid + ' (' + scanCount + '회, hit:' + hitCount + ')\r');
          }
        }

        // 10개마다 DB 배치 저장
        if (batchProducts.length >= 10) {
          const dbResult = saveToDb(batchProducts);
          console.log('  [DB] 배치: +' + dbResult.inserted + ' ~' + dbResult.updated + ' 성분:' + dbResult.ingsSaved);
          batchProducts = [];
        }

        // 진행 상태 저장 (20회마다)
        if (scanCount % 20 === 0) {
          progress.lastScanId = pid;
          progress.scannedIds = Array.from(crawledIds);
          progress.totalCrawled = allProducts.length;
          saveProgress(progress);
        }

        // WAF 감지 방지
        await randomDelay();

        // 50개 연속 404면 스캔 구간 넘어감
        if (consecutive404 >= 50) {
          console.log('\n  [!] 연속 404 ' + consecutive404 + '회 — 다음 구간으로 점프');
          pid += scanStep * 10;
          consecutive404 = 0;
        }
      }

      // 나머지 배치 저장
      if (batchProducts.length > 0) {
        const dbResult = saveToDb(batchProducts);
        console.log('  [DB] 최종 배치: +' + dbResult.inserted + ' ~' + dbResult.updated + ' 성분:' + dbResult.ingsSaved);
      }

      console.log('\n  스캔 결과: ' + scanCount + '회 시도, ' + hitCount + '개 발견 (hit rate: ' + (hitCount / Math.max(scanCount, 1) * 100).toFixed(1) + '%)');
    }

    // ── 최종 저장 ──
    const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const jsonFile = path.join(CONFIG.outputDir, 'hwahae_full_' + timestamp + '.json');
    fs.writeFileSync(jsonFile, JSON.stringify(allProducts, null, 2));

    // 진행 저장
    progress.lastScanId = scanEnd;
    progress.scannedIds = Array.from(crawledIds);
    progress.totalCrawled += allProducts.length;
    saveProgress(progress);

    const withIng = allProducts.filter(p => p.ingredients?.length > 0).length;
    const withImg = allProducts.filter(p => p.image_local).length;

    console.log('\n============================================');
    console.log('  크롤링 완료 (' + elapsed + '분)');
    console.log('  제품: ' + allProducts.length + '개');
    console.log('  전성분: ' + withIng + '개 제품');
    console.log('  이미지: ' + withImg + '개');
    console.log('  JSON: ' + jsonFile);
    console.log('  누적: ' + progress.totalCrawled + '개');
    console.log('============================================');

  } catch (e) {
    console.error('\n크롤링 에러: ' + e.message);
    // 에러 시에도 진행 저장
    progress.scannedIds = Array.from(crawledIds);
    saveProgress(progress);
  } finally {
    await browser.close();
  }
}

main().catch(console.error);
