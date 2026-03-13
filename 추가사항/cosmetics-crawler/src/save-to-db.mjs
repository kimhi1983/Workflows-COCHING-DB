/**
 * 크롤링 결과 JSON → PostgreSQL product_master 저장
 * 사용법: node src/save-to-db.mjs <json파일>
 * 예시:  node src/save-to-db.mjs output/hwahae_크림_2026-03-13T02-29-00.json
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

let inserted = 0;
let updated = 0;
let skipped = 0;

for (const p of data) {
  const brandName = (p.brand || '').replace(/'/g, "''").slice(0, 255);
  const productName = (p.name || '').replace(/'/g, "''").slice(0, 500);
  const category = (p.category || '').replace(/'/g, "''").slice(0, 255);
  const imageUrl = (p.thumbnail_url || p.full_image_url || '').replace(/'/g, "''");
  const imageLocal = (p.image_local || '').replace(/'/g, "''");
  const price = p.price ? parseFloat(p.price) : null;
  const rating = p.rating ? parseFloat(p.rating) : null;
  const hwahaeUrl = (p.hwahae_url || '').replace(/'/g, "''");

  if (!brandName || !productName) {
    skipped++;
    continue;
  }

  // UPSERT: 이미 있으면 image_url만 업데이트
  const sql = `
    INSERT INTO product_master (brand_name, product_name, category, image_url, retail_price_usd, source, data_quality_grade, brand_website)
    VALUES ('${brandName}', '${productName}', '${category}', '${imageUrl}', ${price || 'NULL'}, 'hwahae', 'B', '${hwahaeUrl}')
    ON CONFLICT (brand_name, product_name)
    DO UPDATE SET
      image_url = EXCLUDED.image_url,
      category = COALESCE(NULLIF(EXCLUDED.category, ''), product_master.category),
      retail_price_usd = COALESCE(EXCLUDED.retail_price_usd, product_master.retail_price_usd),
      brand_website = EXCLUDED.brand_website,
      updated_at = NOW()
    RETURNING (xmax = 0) AS is_insert;
  `.trim();

  try {
    const result = execSync(PSQL + " -c \"" + sql.replace(/"/g, '\\"').replace(/\n/g, ' ') + "\"", { encoding: 'utf-8' }).trim();
    if (result === 't') {
      inserted++;
      console.log('  + INSERT: ' + brandName + ' - ' + productName.slice(0, 40));
    } else {
      updated++;
      console.log('  ~ UPDATE: ' + brandName + ' - ' + productName.slice(0, 40));
    }
  } catch (e) {
    console.log('  ! ERROR: ' + brandName + ' - ' + productName.slice(0, 40) + ' → ' + e.message.split('\n')[0]);
    skipped++;
  }
}

console.log('\n============================================');
console.log('  DB 저장 완료');
console.log('  INSERT: ' + inserted + '건');
console.log('  UPDATE: ' + updated + '건');
console.log('  SKIP:   ' + skipped + '건');
console.log('============================================');
