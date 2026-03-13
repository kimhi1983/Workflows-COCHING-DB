/**
 * 크롤링 결과 JSON → PostgreSQL 저장
 * - product_master: 제품 정보 UPSERT
 * - product_ingredients: 전성분 매핑 저장
 * - ingredient_master: EWG/용도 업데이트
 *
 * 사용법: node src/save-to-db.mjs <json파일>
 */
import fs from 'fs';
import { execSync } from 'child_process';

const jsonFile = process.argv[2];
if (!jsonFile) {
  console.error('Usage: node src/save-to-db.mjs <json파일>');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(jsonFile, 'utf-8'));
console.log('제품 ' + data.length + '개 DB 저장 시작...');

const PGPASS = '/tmp/pgpass';
const PSQL = 'PGPASSFILE=' + PGPASS + ' psql -h 127.0.0.1 -U coching_user -d coching_db -t -A';

// pgpass 설정
execSync("printf '127.0.0.1:5432:coching_db:coching_user:coching2026!' > " + PGPASS + " && chmod 600 " + PGPASS);

function esc(s) { return (s || '').replace(/'/g, "''"); }

function runSQL(sql) {
  return execSync(PSQL + " -c \"" + sql.replace(/"/g, '\\"').replace(/\n/g, ' ') + "\"", { encoding: 'utf-8' }).trim();
}

let inserted = 0;
let updated = 0;
let skipped = 0;
let ingsSaved = 0;
let ingsMasterUpdated = 0;

for (const p of data) {
  const brandName = esc(p.brand).slice(0, 255);
  const productName = esc(p.name).slice(0, 500);
  const category = esc(p.category).slice(0, 255);
  const imageUrl = esc(p.thumbnail_url || p.full_image_url);
  const price = p.price ? parseFloat(p.price) : null;
  const hwahaeUrl = esc(p.hwahae_url);

  if (!brandName || !productName) {
    skipped++;
    continue;
  }

  // 1. product_master UPSERT
  const sql = `INSERT INTO product_master (brand_name, product_name, category, image_url, retail_price_usd, source, data_quality_grade, brand_website) VALUES ('${brandName}', '${productName}', '${category}', '${imageUrl}', ${price || 'NULL'}, 'hwahae', 'B', '${hwahaeUrl}') ON CONFLICT (brand_name, product_name) DO UPDATE SET image_url = EXCLUDED.image_url, category = COALESCE(NULLIF(EXCLUDED.category, ''), product_master.category), retail_price_usd = COALESCE(EXCLUDED.retail_price_usd, product_master.retail_price_usd), brand_website = EXCLUDED.brand_website, updated_at = NOW() RETURNING id, (xmax = 0) AS is_insert;`;

  let productId = null;
  try {
    const result = runSQL(sql);
    const parts = result.split('|');
    productId = parseInt(parts[0]);
    const isInsert = parts[1] === 't';
    if (isInsert) {
      inserted++;
      console.log('  + INSERT: ' + brandName + ' - ' + productName.slice(0, 40));
    } else {
      updated++;
      console.log('  ~ UPDATE: ' + brandName + ' - ' + productName.slice(0, 40));
    }
  } catch (e) {
    console.log('  ! ERROR: ' + brandName + ' - ' + productName.slice(0, 40) + ' > ' + e.message.split('\n')[0]);
    skipped++;
    continue;
  }

  // 2. product_ingredients 저장
  const ings = p.ingredients || [];
  if (productId && ings.length > 0) {
    for (const ing of ings) {
      const nameKo = esc(ing.name_ko).slice(0, 255);
      const nameInci = esc(ing.name_inci).slice(0, 255);
      const ewg = ing.ewg_grade != null ? ing.ewg_grade : 'NULL';
      const purpose = esc(ing.purpose).slice(0, 500);
      const order = ing.order || 'NULL';

      if (!nameInci && !nameKo) continue;

      const ingSql = `INSERT INTO product_ingredients (product_id, ingredient_order, ingredient_name_ko, ingredient_name_inci, ewg_grade, purpose) VALUES (${productId}, ${order}, '${nameKo}', '${nameInci}', ${ewg}, '${purpose}') ON CONFLICT (product_id, ingredient_name_inci) DO UPDATE SET ewg_grade = EXCLUDED.ewg_grade, purpose = EXCLUDED.purpose, ingredient_order = EXCLUDED.ingredient_order;`;

      try {
        runSQL(ingSql);
        ingsSaved++;
      } catch (e) { /* skip duplicate */ }

      // 3. ingredient_master EWG/용도 업데이트 (INCI명 매칭)
      if (nameInci && ewg !== 'NULL') {
        const updateSql = `UPDATE ingredient_master SET ewg_score = ${ewg}, purpose = COALESCE(NULLIF('${purpose}', ''), purpose), hwahae_id = ${ing.id || 'NULL'}, updated_at = NOW() WHERE LOWER(inci_name) = LOWER('${nameInci}') AND (ewg_score IS NULL OR ewg_score != ${ewg});`;
        try {
          const res = runSQL(updateSql);
          if (res && !res.startsWith('UPDATE 0')) ingsMasterUpdated++;
        } catch (e) { /* skip */ }
      }
    }
    console.log('    -> 전성분 ' + ings.length + '개 저장');
  }
}

console.log('\n============================================');
console.log('  DB 저장 완료');
console.log('  제품 INSERT: ' + inserted + '건');
console.log('  제품 UPDATE: ' + updated + '건');
console.log('  제품 SKIP:   ' + skipped + '건');
console.log('  전성분 저장: ' + ingsSaved + '건');
console.log('  원료DB EWG 업데이트: ' + ingsMasterUpdated + '건');
console.log('============================================');
