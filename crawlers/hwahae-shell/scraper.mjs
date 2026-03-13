#!/usr/bin/env node
/**
 * 화해(Hwahae) 직접 스크래퍼
 * 화해 웹사이트에서 제품 이미지 + 전성분 수집
 * 
 * 사용법: node scraper.mjs <검색어> [출력폴더]
 * 예시:  node scraper.mjs "선크림" ./output
 */

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

const query = process.argv[2] || '크림';
const outputDir = process.argv[3] || './output';

if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

// ── HTTP 요청 유틸 ─────────────────────────────────────
function fetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
        'Referer': 'https://www.hwahae.co.kr/',
        ...options.headers,
      },
      timeout: 15000,
    }, (res) => {
      // 리다이렉트 처리
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetch(res.headers.location, options).then(resolve).catch(reject);
      }
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, body: data, headers: res.headers }));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
  });
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ── 화해 검색 페이지 스크래핑 ────────────────────────────
async function searchHwahae(keyword) {
  console.log(`\n🔍 화해 검색: "${keyword}"`);
  
  const searchUrl = `https://www.hwahae.co.kr/search?query=${encodeURIComponent(keyword)}`;
  console.log(`   URL: ${searchUrl}`);

  try {
    const res = await fetch(searchUrl);
    console.log(`   HTTP ${res.status}, 본문 ${res.body.length} bytes`);

    // HTML에서 제품 데이터 추출 시도
    const products = [];

    // 방법 1: __NEXT_DATA__ (Next.js 앱인 경우)
    const nextDataMatch = res.body.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (nextDataMatch) {
      console.log('   ✅ Next.js 데이터 발견');
      try {
        const nextData = JSON.parse(nextDataMatch[1]);
        console.log('   📦 __NEXT_DATA__ 키:', Object.keys(nextData.props?.pageProps || {}).join(', '));
        
        // 페이지 데이터에서 제품 목록 추출
        const pageProps = nextData.props?.pageProps || {};
        const productList = pageProps.products || pageProps.items || 
                           pageProps.searchResult?.products || 
                           pageProps.data?.products || [];
        
        if (Array.isArray(productList)) {
          for (const p of productList) {
            products.push({
              id: p.id || p.productId,
              title: p.title || p.name || p.productName,
              brand: p.brand || p.brandName,
              price: p.price || p.salePrice,
              imageUrl: p.imageUrl || p.thumbnailImage || p.image,
              rating: p.rating || p.averageRating,
              reviewCount: p.reviewCount,
              ingredients: p.ingredients || p.ingredientList || null,
              detailUrl: p.detailUrl || (p.id ? `https://www.hwahae.co.kr/products/${p.id}` : null),
              source: 'next_data',
            });
          }
        }

        // 깊은 탐색
        if (products.length === 0) {
          const allStr = JSON.stringify(nextData);
          console.log('   🔎 제품 데이터 심층 탐색 중...');
          
          // productId 패턴 찾기
          const idMatches = allStr.match(/"(?:product)?[Ii]d"\s*:\s*(\d+)/g);
          if (idMatches) {
            console.log(`   발견된 ID 패턴: ${idMatches.length}개`);
          }
        }
      } catch (e) {
        console.log(`   ⚠️ Next.js 파싱 에러: ${e.message}`);
      }
    }

    // 방법 2: JSON-LD 구조화 데이터
    const jsonLdMatches = res.body.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g);
    if (jsonLdMatches) {
      console.log(`   ✅ JSON-LD 데이터 ${jsonLdMatches.length}개 발견`);
      for (const m of jsonLdMatches) {
        try {
          const content = m.replace(/<\/?script[^>]*>/g, '');
          const ld = JSON.parse(content);
          if (ld['@type'] === 'Product' || ld['@type'] === 'ItemList') {
            console.log(`   📦 JSON-LD 타입: ${ld['@type']}`);
          }
        } catch (e) {}
      }
    }

    // 방법 3: 인라인 스크립트에서 window.__STATE__ 등
    const stateMatches = res.body.match(/window\.__(?:STATE|INITIAL_STATE|DATA)__\s*=\s*({[\s\S]*?});?\s*<\/script>/);
    if (stateMatches) {
      console.log('   ✅ window.__STATE__ 발견');
      try {
        const state = JSON.parse(stateMatches[1]);
        console.log('   📦 State 키:', Object.keys(state).slice(0, 10).join(', '));
      } catch (e) {}
    }

    // 방법 4: HTML 메타 태그에서 정보 추출
    const ogTitle = res.body.match(/<meta property="og:title" content="([^"]+)"/);
    const ogImage = res.body.match(/<meta property="og:image" content="([^"]+)"/);
    if (ogTitle) console.log(`   📌 OG Title: ${ogTitle[1]}`);
    if (ogImage) console.log(`   📌 OG Image: ${ogImage[1]}`);

    // 방법 5: API 엔드포인트 추출 시도
    const apiMatches = res.body.match(/["'](\/api\/[^"']+|https?:\/\/[^"']*api[^"']*hwahae[^"']+)["']/g);
    if (apiMatches) {
      const uniqueApis = [...new Set(apiMatches.map(m => m.replace(/["']/g, '')))];
      console.log(`\n   🌐 발견된 API 엔드포인트:`);
      uniqueApis.forEach(api => console.log(`      ${api}`));
    }

    // HTML 구조 분석
    console.log('\n   📊 HTML 구조 분석:');
    const scriptTags = (res.body.match(/<script[^>]*>/g) || []).length;
    const hasSPA = res.body.includes('__next') || res.body.includes('__nuxt') || res.body.includes('root');
    console.log(`      script 태그: ${scriptTags}개`);
    console.log(`      SPA 감지: ${hasSPA ? '예 (클라이언트 렌더링)' : '아니오'}`);
    console.log(`      본문 길이: ${res.body.length} chars`);

    // 결과 저장
    if (products.length > 0) {
      console.log(`\n   ✅ ${products.length}개 제품 수집 완료`);
      products.forEach((p, i) => {
        console.log(`\n   [${i+1}] ${p.brand} - ${p.title}`);
        console.log(`       이미지: ${p.imageUrl ? '✅' : '❌'}`);
        console.log(`       전성분: ${p.ingredients ? '✅' : '❌ (상세 페이지 필요)'}`);
        console.log(`       상세URL: ${p.detailUrl || '?'}`);
      });
    } else {
      console.log('\n   ⚠️ 검색 결과에서 직접 제품 추출 불가');
      console.log('   → 화해는 SPA로 클라이언트 렌더링하므로 Playwright 필요');
      console.log('   → 또는 Apify 스크래퍼 사용 권장');
    }

    // 원본 HTML 저장 (디버깅용)
    const htmlFile = path.join(outputDir, `hwahae_raw_${keyword}_${Date.now()}.html`);
    fs.writeFileSync(htmlFile, res.body);
    console.log(`\n   💾 원본 HTML 저장: ${htmlFile}`);

    // 제품 JSON 저장
    if (products.length > 0) {
      const jsonFile = path.join(outputDir, `hwahae_direct_${keyword}_${Date.now()}.json`);
      fs.writeFileSync(jsonFile, JSON.stringify(products, null, 2));
      console.log(`   💾 제품 JSON 저장: ${jsonFile}`);
    }

    return products;

  } catch (e) {
    console.error(`   ❌ 에러: ${e.message}`);
    return [];
  }
}

// ── 제품 상세 페이지 스크래핑 ─────────────────────────────
async function scrapeProductDetail(productUrl) {
  console.log(`\n📋 제품 상세: ${productUrl}`);

  try {
    const res = await fetch(productUrl);
    console.log(`   HTTP ${res.status}`);

    const product = { url: productUrl };

    // __NEXT_DATA__ 에서 상세 정보
    const nextDataMatch = res.body.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (nextDataMatch) {
      try {
        const nextData = JSON.parse(nextDataMatch[1]);
        const pageProps = nextData.props?.pageProps || {};
        const detail = pageProps.product || pageProps.detail || pageProps.data || pageProps;
        
        product.title = detail.title || detail.name || detail.productName;
        product.brand = detail.brand || detail.brandName;
        product.price = detail.price || detail.salePrice;
        product.imageUrl = detail.imageUrl || detail.image;
        product.images = detail.images || [];
        product.ingredients = detail.ingredients || detail.ingredientList || [];
        product.description = detail.description;
        product.category = detail.category || detail.categoryName;
        product.rating = detail.rating || detail.averageRating;

        console.log(`   ✅ 제품명: ${product.title}`);
        console.log(`   ✅ 이미지: ${product.imageUrl ? '있음' : '없음'}`);
        console.log(`   ✅ 전성분: ${Array.isArray(product.ingredients) ? product.ingredients.length + '개' : '확인필요'}`);
      } catch (e) {
        console.log(`   ⚠️ 파싱 에러: ${e.message}`);
      }
    }

    // OG 메타 태그 보완
    if (!product.title) {
      const m = res.body.match(/<meta property="og:title" content="([^"]+)"/);
      if (m) product.title = m[1];
    }
    if (!product.imageUrl) {
      const m = res.body.match(/<meta property="og:image" content="([^"]+)"/);
      if (m) product.imageUrl = m[1];
    }

    return product;

  } catch (e) {
    console.error(`   ❌ 에러: ${e.message}`);
    return null;
  }
}

// ── 메인 실행 ────────────────────────────────────────────
async function main() {
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('  화해(Hwahae) 직접 스크래퍼');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

  // 1단계: 검색
  const products = await searchHwahae(query);

  // 2단계: 상세 페이지 (제품 URL이 있는 경우)
  if (products.length > 0) {
    console.log('\n━━━ 상세 페이지 스크래핑 ━━━');
    const detailed = [];
    
    for (let i = 0; i < Math.min(products.length, 3); i++) {
      const p = products[i];
      if (p.detailUrl) {
        await sleep(2000); // rate limiting
        const detail = await scrapeProductDetail(p.detailUrl);
        if (detail) detailed.push({ ...p, ...detail });
      }
    }

    if (detailed.length > 0) {
      const file = path.join(outputDir, `hwahae_detailed_${query}_${Date.now()}.json`);
      fs.writeFileSync(file, JSON.stringify(detailed, null, 2));
      console.log(`\n💾 상세 데이터 저장: ${file}`);
    }
  }

  // 3단계: 샘플 제품 URL 직접 테스트
  console.log('\n━━━ 샘플 제품 페이지 구조 분석 ━━━');
  await sleep(2000);
  
  // 화해 인기 제품 URL로 구조 테스트
  const sampleUrls = [
    'https://www.hwahae.co.kr/products/90050',
    'https://www.hwahae.co.kr/products/100001',
  ];

  for (const url of sampleUrls) {
    await sleep(2000);
    const detail = await scrapeProductDetail(url);
    if (detail && detail.title) {
      console.log(`\n   📦 샘플 제품 구조 확인됨`);
      const keys = Object.keys(detail).filter(k => detail[k] != null);
      console.log(`   사용 가능 필드: ${keys.join(', ')}`);
      break;
    }
  }

  console.log('\n━━━ 완료 ━━━');
  console.log(`출력 폴더: ${outputDir}`);
}

main().catch(console.error);
