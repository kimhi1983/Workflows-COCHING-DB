#!/usr/bin/env python3
"""
n8n 워크플로우에 6단계 스킬 파이프라인 적용
- v2.3-A~F: 카테고리×피부타입 가이드 처방
- v1.0: 제품카피 가이드
"""
import sqlite3
import json
import copy
import time
import os

DB_PATH = "/home/kpros/.n8n/database.sqlite"

# ========== 1. 새 프롬프트 (v2.3 가이드처방용) ==========
GUIDE_PROMPT_JS = r'''const config = $('🔄 원료 SQL 생성').first().json;
const ingredients = $('📦 원료 DB 조회').all().map(i=>i.json);
const regulations = $('📋 규제 DB 조회').all().map(i=>i.json);
const refProducts = $('📦 참조제품 조회').all().map(i=>i.json);
const ingList = ingredients.map(i=> i.inci_name+' ('+(i.korean_name||'-')+') CAS:'+(i.cas_number||'-')).join('\n');
const regList = regulations.map(r=> r.inci_name+': '+r.restriction+' (최대 '+(r.max_concentration||'미정')+')').join('\n');
const refList = refProducts.map(p=> p.brand_name+' '+p.product_name+' pH:'+(p.ph_value||'?')+' 점도:'+(p.viscosity_cp||'?')).join('\n');
const prompt = `당신은 화장품 처방 전문가입니다. 아래 6단계 스킬 파이프라인을 반드시 순서대로 적용하세요.

=== SKILL PIPELINE (6단계) ===

[STEP 1: FORMULATION — 처방 설계]
- 제품유형: ${config.product_type_kr}
- 피부타입: ${config.skin_type_kr} (${config.skin_type_eng})
- Phase 구분: A(수상), B(유상), C(기능성), D(첨가제)
- 피부타입별 원료 적합성 반영 (민감성→저자극/무향, 지성→경량오일, 건성→고보습)
- DB 원료 후보를 우선 활용

[STEP 2: COMPOUND-EXPANSION — 복합성분 전개]
- 복합성분 블렌드(Compound) 사용 시 구성 INCI로 전개
- 전개공식: 구성_INCI_wt% = 복합원료_투입wt% × 구성_INCI_비율(fraction)
- 동일 INCI 중복 시 전부 합산 후 단일 항목
- 동일 INCI 다른 등급(Dimethicone 5cSt + 350cSt) → 합산
- 향료(Fragrance/Parfum) → 단일 항목 표기 (전개 안 함)

[STEP 3: PRECISION-ARITHMETIC — 정수 연산]
★★★ 가장 중요 ★★★
- 모든 wt%를 정수(×100)로 변환 후 합산 (부동소수점 오차 방지)
- int_value = round(wt% × 100)
- 밸런스 역산: aqua_int = 10000 - sum(비Aqua 성분 int값)
- 3단계 검증:
  검증1: sum(all_int) == 10000
  검증2: sum/100 == 100.00
  검증3: Aqua_int == 역산값
- 복합성분 내 Aqua는 밸런스 역산에서 제외, 최종 출력 시 합산
- 반올림 오차 → Largest Remainder Method로 보정

[STEP 4: INGREDIENTS — 성분 안전성]
- 배합 한도 준수 확인 (자외선차단제, 방부제 등)
- 피부타입별 부적합 성분 회피
- 성분 간 비호환 조합 체크

[STEP 5: REGULATION — 규제 적합성]
- 한국 식약처: 배합 금지/한도 원료, 전성분 표시 기준
- 전성분: 함량 내림차순(1% 초과), 1% 이하 순서 무관
- 나노 원료 사용 시 표기

[STEP 6: QA-VALIDATION — 품질 검증]
- 처방서(투입 기준) + 전성분(표기 기준) 이중 문서 교차 확인
- 총 wt% = 100.00% (처방서 = 전성분 동일)
- 배합 금지 성분 없음 확인

=== 참조 데이터 ===

[DB 원료 후보]
${ingList || '(DB 원료 없음 - 일반 지식 활용)'}

[규제 제한]
${regList || '(규제 정보 없음)'}

[참조 제품]
${refList || '(참조 제품 없음)'}

=== 출력 형식 ===

반드시 다음 JSON 구조로 출력하세요:
{"formula_name":"처방명","product_type":"${config.product_type_kr}","skin_type":"${config.skin_type_kr}",
"phases":[{"phase":"A (수상)","temperature":"70-75도","ingredients":[{"inci_name":"INCI명","korean_name":"한글명","wt_percent":숫자,"function":"기능"}]}],
"inci_list":[{"inci_name":"INCI명","wt_percent":숫자,"note":"합산/전개/밸런스 등"}],
"compound_expansion":[{"trade_name":"복합원료명","input_wt":숫자,"components":[{"inci":"INCI","fraction":0.85,"expanded_wt":숫자}]}],
"precision_check":{"int_sum":10000,"wt_sum":"100.00","aqua_int":숫자,"aqua_reverse":숫자,"pass":true},
"process_steps":["단계1","단계2"],
"quality_checks":["검사1","검사2"],
"estimated_ph":5.5,"estimated_viscosity_cp":숫자,
"total_ingredients":숫자,"total_wt_percent":100.00,
"notes":"처방 설명 + 스킬 적용 내역"}

★ 핵심 규칙:
1. 전체 배합비 합계 = 반드시 100.00% (정수합 10000)
2. 정제수는 밸런스 역산으로 결정
3. 복합성분 사용 시 compound_expansion 필드에 전개 내역 기록
4. precision_check 필드에 3단계 검증 결과 기록
5. inci_list 필드에 전성분 표기(함량 내림차순) 기록
6. JSON만 출력하세요.`;
const b64 = Buffer.from(prompt,'utf-8').toString('base64');
return [{json:{...config, prompt_b64: b64, prompt_length: prompt.length}}];'''

# ========== 2. 새 파싱 & 검증 로직 (정수 검증 강화) ==========
PARSE_VALIDATE_JS = r'''const input = $input.first().json;
const config = $('🧠 Claude 프롬프트 구성').first().json;
let guide = {};
try {
  const stdout = (input.stdout||'').trim();
  let jsonStr = stdout.replace(/```json\s*/g,'').replace(/```\s*/g,'').trim();
  const jsonMatch = jsonStr.match(/\{[\s\S]*\}/);
  if (jsonMatch) { guide = JSON.parse(jsonMatch[0]); }
  else { guide = JSON.parse(jsonStr); }
} catch(e) {
  guide = {
    product_type:config.product_type_kr, skin_type:config.skin_type_kr,
    formula_name:config.combo_key+' (파싱실패)',
    raw_output:(input.stdout||'').substring(0,3000), parse_error:e.message
  };
}

// === PRECISION-ARITHMETIC 정수 검증 ===
let totalInt = 0;
let totalWt = 0;
if (guide.phases) {
  guide.phases.forEach(ph=>{
    (ph.ingredients||[]).forEach(ing=>{
      const wt = parseFloat(ing.wt_percent)||0;
      totalInt += Math.round(wt * 100);
      totalWt += wt;
    });
  });
}

// 3단계 검증
const intValid = totalInt === 10000;
const wtValid = Math.abs(totalWt - 100) < 0.05;
const precisionPass = guide.precision_check ? guide.precision_check.pass === true : false;

// wt_valid 판정: 정수합 10000 또는 wt%합 100±0.05 둘 중 하나 만족
const isValid = intValid || wtValid;

// 복합성분 전개 내역 확인
const hasCompound = guide.compound_expansion && guide.compound_expansion.length > 0;
const hasInciList = guide.inci_list && guide.inci_list.length > 0;

// 스킬 적용 메타데이터
if (!guide.skill_pipeline) {
  guide.skill_pipeline = {
    version: "v2.3-skill",
    steps: ["formulation","compound-expansion","precision-arithmetic","ingredients","regulation","qa-validation"],
    compound_expanded: hasCompound,
    inci_list_generated: hasInciList,
    precision_int_sum: totalInt,
    precision_wt_sum: parseFloat(totalWt.toFixed(2)),
    precision_valid: isValid
  };
}

const guideJson = JSON.stringify(guide);
const guideEscaped = guideJson.replace(/'/g,"''");
const fileB64 = Buffer.from(guideJson,'utf-8').toString('base64');
return [{json:{
  combo_key:config.combo_key,
  product_type_kr:config.product_type_kr, skin_type_kr:config.skin_type_kr,
  guide_data_escaped:guideEscaped,
  formula_name:(guide.formula_name||config.combo_key).replace(/'/g,"''"),
  total_wt_percent:totalWt.toFixed(2),
  wt_valid:isValid,
  estimated_ph:guide.estimated_ph||null,
  estimated_viscosity:guide.estimated_viscosity_cp||null,
  has_error:!!guide.parse_error,
  has_compound:hasCompound,
  has_inci_list:hasInciList,
  int_sum:totalInt,
  file_b64:fileB64
}}];'''

# ========== 3. 제품카피 v1.0 용 프롬프트 ==========
COPY_PROMPT_JS = r'''const config = $('🔄 규제 SQL 생성').first().json;
const regulations = $('📋 규제 DB 조회').all().map(i=>i.json);
const regList = regulations.filter(r=>r.inci_name).map(r=> r.inci_name+': '+r.restriction+' (최대 '+(r.max_concentration||'미정')+')').join('\n');
const prompt = `당신은 화장품 처방 역설계(reverse formulation) 전문가입니다.
아래 6단계 스킬 파이프라인을 반드시 순서대로 적용하세요.

=== SKILL PIPELINE (6단계) ===

[STEP 1: FORMULATION — 역처방 설계]
- 원본 제품: ${config.prod_name} (${config.company_name})
- 전성분 리스트를 분석하여 투입 원료 + wt% 역추정
- 전성분 표기 규칙: 1% 초과 내림차순, 1% 이하 순서 무관
- 정제수(Water/Aqua)는 보통 60-80%

[STEP 2: COMPOUND-EXPANSION — 복합성분 역추정]
- 복합성분 블렌드 가능성 검토 (예: 유화제 블렌드, 방부제 블렌드)
- 투입 기준 처방서에는 상품명(Trade Name)으로, 전성분에는 구성 INCI로 표기
- 동일 INCI가 여러 출처에서 나올 수 있음 → 합산 고려

[STEP 3: PRECISION-ARITHMETIC — 정수 연산]
★★★ 가장 중요 ★★★
- 모든 wt%를 정수(×100)로 변환 후 합산
- int_value = round(wt% × 100)
- 밸런스 역산: aqua_int = 10000 - sum(비Aqua int값)
- 3단계 검증: sum(int)==10000, sum/100==100.00, Aqua역산 일치
- 반올림 오차 → Largest Remainder Method 보정

[STEP 4: INGREDIENTS — 성분 안전성]
- 배합 한도 준수, 성분 간 호환성 확인

[STEP 5: REGULATION — 규제 적합성]
- 한국 식약처 배합 금지/한도 원료 확인

[STEP 6: QA-VALIDATION — 품질 검증]
- 총 wt% = 100.00% 확인
- 모든 전성분이 누락 없이 포함되었는지 확인

=== 원본 전성분 ===

[전성분 리스트 (배합비 순서)]
${config.inci_list_str}

[규제 제한]
${regList || '(규제 정보 없음)'}

=== 출력 형식 ===

반드시 다음 JSON으로 출력:
{"formula_name":"[카피] ${config.prod_name}",
"original_product":"${config.prod_name}",
"original_company":"${config.company_name}",
"product_type":"역추정",
"phases":[{"phase":"A (수상)","temperature":"70-75도","ingredients":[{"inci_name":"INCI명","korean_name":"한글명","wt_percent":숫자,"function":"기능"}]}],
"inci_list":[{"inci_name":"INCI명","wt_percent":숫자,"note":"비고"}],
"compound_expansion":[],
"precision_check":{"int_sum":10000,"wt_sum":"100.00","aqua_int":숫자,"aqua_reverse":숫자,"pass":true},
"process_steps":["단계1","단계2"],
"quality_checks":["검사1"],
"estimated_ph":5.5,"estimated_viscosity_cp":숫자,
"total_ingredients":${config.inci_count},
"total_wt_percent":100.00,
"notes":"역추정 근거 + 스킬 적용 내역",
"confidence":"high/medium/low"}

★ 핵심: 배합비 합계 = 반드시 100.00% (정수합 10000). 모든 전성분 포함. JSON만 출력.`;
const b64 = Buffer.from(prompt,'utf-8').toString('base64');
return [{json:{...config, prompt_b64: b64, prompt_length: prompt.length}}];'''

# ========== 4. 제품카피 파싱 검증 ==========
COPY_PARSE_JS = r'''const input = $input.first().json;
const config = $('🧠 Claude 프롬프트 구성').first().json;
let guide = {};
try {
  const stdout = (input.stdout||'').trim();
  let jsonStr = stdout.replace(/```json\s*/g,'').replace(/```\s*/g,'').trim();
  const jsonMatch = jsonStr.match(/\{[\s\S]*\}/);
  if (jsonMatch) { guide = JSON.parse(jsonMatch[0]); }
  else { guide = JSON.parse(jsonStr); }
} catch(e) {
  guide = {
    original_product:config.prod_name, product_type:'역추정',
    formula_name:'[카피] '+config.prod_name+' (파싱실패)',
    raw_output:(input.stdout||'').substring(0,3000), parse_error:e.message
  };
}

// === PRECISION-ARITHMETIC 정수 검증 ===
let totalInt = 0;
let totalWt = 0;
if (guide.phases) {
  guide.phases.forEach(ph=>{
    (ph.ingredients||[]).forEach(ing=>{
      const wt = parseFloat(ing.wt_percent)||0;
      totalInt += Math.round(wt * 100);
      totalWt += wt;
    });
  });
}
const isValid = totalInt === 10000 || Math.abs(totalWt - 100) < 0.05;

if (!guide.skill_pipeline) {
  guide.skill_pipeline = {
    version: "v1.0-skill",
    steps: ["formulation","compound-expansion","precision-arithmetic","ingredients","regulation","qa-validation"],
    precision_int_sum: totalInt,
    precision_wt_sum: parseFloat(totalWt.toFixed(2)),
    precision_valid: isValid
  };
}

const guideJson = JSON.stringify(guide);
const guideEscaped = guideJson.replace(/'/g,"''");
const fileB64 = Buffer.from(guideJson,'utf-8').toString('base64');
return [{json:{
  source_product_id:config.source_product_id,
  source:config.source||'coching_db',
  original_product_name:(guide.original_product||config.prod_name).replace(/'/g,"''"),
  formula_name:(guide.formula_name||'[카피] '+config.prod_name).replace(/'/g,"''"),
  guide_data_escaped:guideEscaped,
  total_wt_percent:totalWt.toFixed(2),
  wt_valid:isValid,
  estimated_ph:guide.estimated_ph||null,
  confidence:guide.confidence||'unknown',
  has_error:!!guide.parse_error,
  int_sum:totalInt,
  file_b64:fileB64
}}];'''


def update_workflows():
    """n8n 워크플로우 업데이트"""

    # v2.3 워크플로우 IDs
    v23_ids = [
        '84c2ce341e9a4b27b735',  # A 기초화장
        'b98f0e27d8d94d5f96a5',  # B 세정
        '079972e71bef4f66bd48',  # C 선케어
        '2fa9c77cdf6641aeb01d',  # D 색조
        '8dd0884072f54d438ffe',  # E 두발
        '41c14d5b1e524695b9d8',  # F 기타
    ]
    copy_id = 'a0670dfdacb34ce887a3'  # 제품카피 v1.0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    updated = 0

    # === v2.3 워크플로우 6개 업데이트 ===
    for wf_id in v23_ids:
        cursor.execute("SELECT name, nodes FROM workflow_entity WHERE id=?", (wf_id,))
        row = cursor.fetchone()
        if not row:
            print(f"  ❌ {wf_id} 미발견")
            continue

        wf_name, nodes_json = row
        nodes = json.loads(nodes_json)
        changed = False

        for node in nodes:
            # 프롬프트 구성 노드 업데이트
            if node.get('name') == '🧠 Claude 프롬프트 구성':
                node['parameters']['jsCode'] = GUIDE_PROMPT_JS
                changed = True
                print(f"  ✅ {wf_name} — 프롬프트 업데이트")

            # 파싱 & 검증 노드 업데이트
            if node.get('name') == '🔄 처방 파싱 & 검증':
                node['parameters']['jsCode'] = PARSE_VALIDATE_JS
                changed = True
                print(f"  ✅ {wf_name} — 파싱검증 업데이트")

        if changed:
            cursor.execute(
                "UPDATE workflow_entity SET nodes=?, updatedAt=datetime('now') WHERE id=?",
                (json.dumps(nodes, ensure_ascii=False), wf_id)
            )
            updated += 1

    # === 제품카피 v1.0 업데이트 ===
    cursor.execute("SELECT name, nodes FROM workflow_entity WHERE id=?", (copy_id,))
    row = cursor.fetchone()
    if row:
        wf_name, nodes_json = row
        nodes = json.loads(nodes_json)
        changed = False

        for node in nodes:
            if node.get('name') == '🧠 Claude 프롬프트 구성':
                node['parameters']['jsCode'] = COPY_PROMPT_JS
                changed = True
                print(f"  ✅ {wf_name} — 프롬프트 업데이트")

            # 제품카피 파싱 노드 이름 확인
            if '파싱' in node.get('name', '') and '검증' in node.get('name', ''):
                node['parameters']['jsCode'] = COPY_PARSE_JS
                changed = True
                print(f"  ✅ {wf_name} — 파싱검증 업데이트")

        if changed:
            cursor.execute(
                "UPDATE workflow_entity SET nodes=?, updatedAt=datetime('now') WHERE id=?",
                (json.dumps(nodes, ensure_ascii=False), copy_id)
            )
            updated += 1

    conn.commit()
    conn.close()

    print(f"\n총 {updated}개 워크플로우 업데이트 완료")
    return updated


if __name__ == '__main__':
    print("=" * 60)
    print("n8n 워크플로우 6단계 스킬 파이프라인 적용")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"❌ DB 파일 미발견: {DB_PATH}")
        exit(1)

    update_workflows()
    print("\n✅ 완료. n8n 재시작 필요: pm2 restart n8n")
