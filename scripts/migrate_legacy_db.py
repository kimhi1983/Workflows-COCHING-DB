#!/usr/bin/env python3
"""
기존 DB 자료 → public 스키마 통합 마이그레이션
1. compound_master 테이블 생성 + 복합원료 데이터 적재
2. t_coos_ingd → ingredient_master 통합 (25,643건)
3. t_coos_prod → product_master 통합 (16,138건)
"""
import psycopg2
import json

DB = dict(host='127.0.0.1', port=5432, dbname='coching_db',
          user='coching_user', password='coching2026!')

def run():
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    cur = conn.cursor()

    # ================================================================
    # STEP 1: compound_master 테이블 생성 + 복합원료 데이터
    # ================================================================
    print("=" * 60)
    print("[STEP 1] compound_master 테이블 생성")
    print("=" * 60)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS compound_master (
        id              SERIAL PRIMARY KEY,
        trade_name      VARCHAR(255) NOT NULL,
        supplier        VARCHAR(255),
        category        VARCHAR(100),
        total_fraction  NUMERIC(5,3) DEFAULT 1.000,
        components      JSONB NOT NULL,
        notes           TEXT,
        source          VARCHAR(50) DEFAULT 'manual',
        created_at      TIMESTAMP DEFAULT now(),
        updated_at      TIMESTAMP DEFAULT now(),
        UNIQUE(trade_name)
    );
    CREATE INDEX IF NOT EXISTS idx_cm_trade ON compound_master(trade_name);
    CREATE INDEX IF NOT EXISTS idx_cm_supplier ON compound_master(supplier);
    CREATE INDEX IF NOT EXISTS idx_cm_category ON compound_master(category);
    """)

    # 복합원료 기본 데이터 (SKILL20260309.md 기반 + 확장)
    compounds = [
        ("Bentone Gel MIO", "Elementis", "실리콘 겔베이스",
         json.dumps([
             {"inci": "Cyclopentasiloxane", "fraction": 0.850, "korean": "사이클로펜타실록세인"},
             {"inci": "Disteardimonium Hectorite", "fraction": 0.100, "korean": "디스테아디모늄헥토라이트"},
             {"inci": "Propylene Carbonate", "fraction": 0.050, "korean": "프로필렌카보네이트"}
         ]), "W/Si 쿠션·파운데이션용 겔베이스"),

        ("Dow Corning 9040 Silicone Elastomer Blend", "Dow", "실리콘 에멀전",
         json.dumps([
             {"inci": "Cyclopentasiloxane", "fraction": 0.880, "korean": "사이클로펜타실록세인"},
             {"inci": "Dimethicone/Vinyl Dimethicone Crosspolymer", "fraction": 0.120, "korean": "디메치콘/비닐디메치콘크로스폴리머"}
         ]), "실리콘 엘라스토머, 부드러운 사용감"),

        ("Olivem 1000", "Hallstar", "O/W 유화제",
         json.dumps([
             {"inci": "Cetearyl Olivate", "fraction": 0.500, "korean": "세테아릴올리베이트"},
             {"inci": "Sorbitan Olivate", "fraction": 0.500, "korean": "소르비탄올리베이트"}
         ]), "올리브 유래 자연 유화제"),

        ("Emulsimousse", "Gattefossé", "O/W 유화제",
         json.dumps([
             {"inci": "Glyceryl Stearate", "fraction": 0.400, "korean": "글리세릴스테아레이트"},
             {"inci": "PEG-100 Stearate", "fraction": 0.350, "korean": "피이지-100스테아레이트"},
             {"inci": "Potassium Cetyl Phosphate", "fraction": 0.250, "korean": "포타슘세틸포스페이트"}
         ]), "무스 텍스처 유화제"),

        ("Euxyl PE 9010", "Schülke", "방부제 블렌드",
         json.dumps([
             {"inci": "Phenoxyethanol", "fraction": 0.900, "korean": "페녹시에탄올"},
             {"inci": "Ethylhexylglycerin", "fraction": 0.100, "korean": "에틸헥실글리세린"}
         ]), "파라벤-프리 방부제 시스템"),

        ("Optiphen Plus", "Ashland", "방부제 블렌드",
         json.dumps([
             {"inci": "Phenoxyethanol", "fraction": 0.700, "korean": "페녹시에탄올"},
             {"inci": "Caprylyl Glycol", "fraction": 0.200, "korean": "카프릴릴글라이콜"},
             {"inci": "Sorbic Acid", "fraction": 0.100, "korean": "소르빅애씨드"}
         ]), "파라벤-프리 보존제"),

        ("Tinosorb M", "BASF", "자외선차단 분산체",
         json.dumps([
             {"inci": "Methylene Bis-Benzotriazolyl Tetramethylbutylphenol", "fraction": 0.500, "korean": "메틸렌비스벤조트리아졸릴테트라메틸부틸페놀"},
             {"inci": "Water", "fraction": 0.400, "korean": "정제수"},
             {"inci": "Decyl Glucoside", "fraction": 0.100, "korean": "데실글루코사이드"}
         ]), "광범위 UVA/UVB 차단 나노 분산체"),

        ("Sepigel 305", "Seppic", "증점 유화제",
         json.dumps([
             {"inci": "Polyacrylamide", "fraction": 0.400, "korean": "폴리아크릴아마이드"},
             {"inci": "C13-14 Isoparaffin", "fraction": 0.350, "korean": "C13-14아이소파라핀"},
             {"inci": "Laureth-7", "fraction": 0.250, "korean": "라우레스-7"}
         ]), "즉시 증점 에멀전 안정제"),

        ("Lanol 99", "Seppic", "에스터 오일 블렌드",
         json.dumps([
             {"inci": "Isononyl Isononanoate", "fraction": 0.500, "korean": "아이소노닐아이소노나노에이트"},
             {"inci": "Isodecyl Neopentanoate", "fraction": 0.500, "korean": "아이소데실네오펜타노에이트"}
         ]), "경량 드라이 에스터 오일"),

        ("Montanov 68", "Seppic", "O/W 유화제",
         json.dumps([
             {"inci": "Cetearyl Alcohol", "fraction": 0.500, "korean": "세테아릴알코올"},
             {"inci": "Cetearyl Glucoside", "fraction": 0.500, "korean": "세테아릴글루코사이드"}
         ]), "PEG-프리 자연 유래 유화제"),

        ("Simulgel EG", "Seppic", "증점 안정제",
         json.dumps([
             {"inci": "Hydroxyethyl Acrylate/Sodium Acryloyldimethyl Taurate Copolymer", "fraction": 0.400, "korean": "하이드록시에틸아크릴레이트/소듐아크릴로일디메틸타우레이트코폴리머"},
             {"inci": "Squalane", "fraction": 0.350, "korean": "스쿠알란"},
             {"inci": "Polysorbate 60", "fraction": 0.250, "korean": "폴리소르베이트60"}
         ]), "콜드 프로세스 겔 증점제"),

        ("Tego Care PBS 6", "Evonik", "W/S 유화제",
         json.dumps([
             {"inci": "Lauryl PEG/PPG-18/18 Methicone", "fraction": 0.600, "korean": "라우릴피이지/피피지-18/18메치콘"},
             {"inci": "Dimethicone", "fraction": 0.400, "korean": "디메치콘"}
         ]), "실리콘 기반 W/S 유화제"),

        ("Dermofeel PA-3", "Evonik", "킬레이트제",
         json.dumps([
             {"inci": "Phytic Acid", "fraction": 0.500, "korean": "피틱애씨드"},
             {"inci": "Water", "fraction": 0.450, "korean": "정제수"},
             {"inci": "Sodium Hydroxide", "fraction": 0.050, "korean": "소듐하이드록사이드"}
         ]), "EDTA 대체 천연 킬레이트제"),

        ("Sharomix 705", "Sharon", "방부제 블렌드",
         json.dumps([
             {"inci": "Phenoxyethanol", "fraction": 0.700, "korean": "페녹시에탄올"},
             {"inci": "Chlorphenesin", "fraction": 0.300, "korean": "클로르페네신"}
         ]), "파라벤-프리 방부제 시스템"),

        ("Easynov", "Seppic", "W/O 유화제",
         json.dumps([
             {"inci": "Octyldodecanol", "fraction": 0.400, "korean": "옥틸도데카놀"},
             {"inci": "Octyldodecyl Xyloside", "fraction": 0.350, "korean": "옥틸도데실자일로사이드"},
             {"inci": "PEG-30 Dipolyhydroxystearate", "fraction": 0.250, "korean": "피이지-30디폴리하이드록시스테아레이트"}
         ]), "W/O 콜드 프로세스 유화제"),
    ]

    inserted = 0
    for tn, supplier, cat, comp, notes in compounds:
        cur.execute("""
            INSERT INTO compound_master (trade_name, supplier, category, components, notes, source)
            VALUES (%s, %s, %s, %s::jsonb, %s, 'skill_db')
            ON CONFLICT (trade_name) DO UPDATE SET
                supplier=EXCLUDED.supplier, category=EXCLUDED.category,
                components=EXCLUDED.components, notes=EXCLUDED.notes,
                updated_at=now()
        """, (tn, supplier, cat, comp, notes))
        inserted += 1
    conn.commit()
    print(f"  ✅ compound_master: {inserted}건 적재")

    # ================================================================
    # STEP 2: t_coos_ingd → ingredient_master 통합
    # ================================================================
    print("\n" + "=" * 60)
    print("[STEP 2] t_coos_ingd → ingredient_master 통합 (25,643건)")
    print("=" * 60)

    cur.execute("""
        INSERT INTO ingredient_master (inci_name, korean_name, cas_number, description, source)
        SELECT DISTINCT ON (inci_name)
            inci_name, korean_name, cas_number, description, source
        FROM (
            SELECT
                COALESCE(
                    detail_json->'getSingleIngredient'->'ingredient'->>'INCI',
                    name_en,
                    name
                ) as inci_name,
                name as korean_name,
                NULLIF(detail_json->'getSingleIngredient'->'ingredient'->>'casNo', '') as cas_number,
                COALESCE(
                    detail_json->'getSingleIngredient'->'ingredient'->>'aiDescription',
                    detail_json->'getSingleIngredient'->'ingredient'->>'description'
                ) as description,
                'coching_legacy' as source
            FROM coching.t_coos_ingd
            WHERE COALESCE(
                detail_json->'getSingleIngredient'->'ingredient'->>'INCI',
                name_en, name
            ) IS NOT NULL
            AND COALESCE(
                detail_json->'getSingleIngredient'->'ingredient'->>'INCI',
                name_en, name
            ) != ''
        ) sub
        ORDER BY inci_name, korean_name
        ON CONFLICT (inci_name) DO UPDATE SET
            korean_name = COALESCE(EXCLUDED.korean_name, ingredient_master.korean_name),
            cas_number = COALESCE(EXCLUDED.cas_number, ingredient_master.cas_number),
            description = COALESCE(EXCLUDED.description, ingredient_master.description),
            updated_at = now()
        WHERE ingredient_master.source != 'coching_legacy'
           OR ingredient_master.korean_name IS NULL
    """)
    ingd_count = cur.rowcount
    conn.commit()
    print(f"  ✅ ingredient_master: {ingd_count}건 통합 (중복 제외 UPSERT)")

    # 규제 정보도 함께 이관 (중복 제거)
    cur.execute("""
        INSERT INTO regulation_cache (inci_name, restriction, max_concentration, source)
        SELECT DISTINCT ON (inci_name)
            inci_name, restriction, max_concentration, source
        FROM (
            SELECT
                COALESCE(
                    detail_json->'getSingleIngredient'->'ingredient'->>'INCI',
                    name_en
                ) as inci_name,
                detail_json->'getSingleIngredient'->'ingredient'->>'euRestriction' as restriction,
                NULL::text as max_concentration,
                'coching_legacy' as source
            FROM coching.t_coos_ingd
            WHERE detail_json->'getSingleIngredient'->'ingredient'->>'euRestriction' IS NOT NULL
              AND detail_json->'getSingleIngredient'->'ingredient'->>'euRestriction' != ''
              AND COALESCE(
                    detail_json->'getSingleIngredient'->'ingredient'->>'INCI',
                    name_en
                  ) IS NOT NULL
        ) sub
        ORDER BY inci_name
        ON CONFLICT DO NOTHING
    """)
    reg_count = cur.rowcount
    conn.commit()
    print(f"  ✅ regulation_cache: {reg_count}건 규제정보 추가 이관")

    # ================================================================
    # STEP 3: t_coos_prod → product_master 통합
    # ================================================================
    print("\n" + "=" * 60)
    print("[STEP 3] t_coos_prod → product_master 통합 (16,138건)")
    print("=" * 60)

    cur.execute("""
        INSERT INTO product_master (
            brand_name, product_name, category, full_ingredients,
            key_ingredients, source, data_quality_grade
        )
        SELECT DISTINCT ON (brand_name, product_name)
            brand_name, product_name, category, full_ingredients,
            key_ingredients, source, data_quality_grade
        FROM (
            SELECT
                COALESCE(
                    detail_json::jsonb->'membership'->>'companyName',
                    company_name,
                    '미상'
                ) as brand_name,
                prod_name as product_name,
                COALESCE(detail_json::jsonb->>'type', '미분류') as category,
                array_to_string(
                    ARRAY(SELECT jsonb_array_elements_text(
                        CASE
                            WHEN detail_json::jsonb->'INCIs' IS NOT NULL
                                 AND jsonb_typeof(detail_json::jsonb->'INCIs') = 'array'
                            THEN detail_json::jsonb->'INCIs'
                            ELSE '[]'::jsonb
                        END
                    )), ', '
                ) as full_ingredients,
                CASE
                    WHEN detail_json::jsonb->'mappedINCIs' IS NOT NULL
                         AND jsonb_typeof(detail_json::jsonb->'mappedINCIs') = 'array'
                    THEN detail_json::jsonb->'mappedINCIs'
                    ELSE '[]'::jsonb
                END as key_ingredients,
                'coching_legacy' as source,
                'B' as data_quality_grade
            FROM coching.t_coos_prod
            WHERE prod_name IS NOT NULL AND prod_name != ''
        ) sub
        ORDER BY brand_name, product_name
        ON CONFLICT (brand_name, product_name) DO UPDATE SET
            category = COALESCE(EXCLUDED.category, product_master.category),
            full_ingredients = COALESCE(EXCLUDED.full_ingredients, product_master.full_ingredients),
            key_ingredients = COALESCE(EXCLUDED.key_ingredients, product_master.key_ingredients),
            updated_at = now()
        WHERE product_master.source != 'coching_legacy'
           OR product_master.full_ingredients IS NULL
    """)
    prod_count = cur.rowcount
    conn.commit()
    print(f"  ✅ product_master: {prod_count}건 통합 (중복 제외 UPSERT)")

    # ================================================================
    # 최종 현황
    # ================================================================
    print("\n" + "=" * 60)
    print("[최종 현황]")
    print("=" * 60)

    cur.execute("""
        SELECT 'compound_master' as tbl, COUNT(*) FROM compound_master
        UNION ALL SELECT 'ingredient_master', COUNT(*) FROM ingredient_master
        UNION ALL SELECT 'product_master', COUNT(*) FROM product_master
        UNION ALL SELECT 'regulation_cache', COUNT(*) FROM regulation_cache
        UNION ALL SELECT 'guide_cache', COUNT(*) FROM guide_cache
        UNION ALL SELECT 'guide_cache_copy', COUNT(*) FROM guide_cache_copy
        UNION ALL SELECT 'coching_knowledge_base', COUNT(*) FROM coching_knowledge_base
        ORDER BY 1
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:30s} {row[1]:>8,}건")

    # source별 현황
    print("\n  --- ingredient_master source별 ---")
    cur.execute("SELECT source, COUNT(*) FROM ingredient_master GROUP BY source ORDER BY COUNT(*) DESC")
    for row in cur.fetchall():
        print(f"    {row[0]:20s} {row[1]:>8,}건")

    print("\n  --- product_master source별 ---")
    cur.execute("SELECT source, COUNT(*) FROM product_master GROUP BY source ORDER BY COUNT(*) DESC")
    for row in cur.fetchall():
        print(f"    {row[0]:20s} {row[1]:>8,}건")

    cur.close()
    conn.close()
    print("\n✅ 마이그레이션 완료!")


if __name__ == '__main__':
    run()
