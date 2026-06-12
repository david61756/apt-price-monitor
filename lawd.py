"""시군구명 → 법정동코드 앞 5자리 변환.

sgg_codes.json은 행정표준코드관리시스템(code.go.kr) '법정동코드 전체자료'에서
시군구 레벨(존재)만 추출해 생성한 파일이다.
"""
import json
import sys
from pathlib import Path

_SGG_PATH = Path(__file__).resolve().parent / "sgg_codes.json"
_sgg_map = None


def _load():
    global _sgg_map
    if _sgg_map is None:
        _sgg_map = json.loads(_SGG_PATH.read_text(encoding="utf-8"))
    return _sgg_map


def resolve_lawd_cd(region):
    """'인천 연수구', '인천광역시 연수구', '성남시 분당구' 등을 5자리 코드로 변환."""
    sgg = _load()
    region = " ".join(region.split())
    if region in sgg:
        return sgg[region]

    q_tokens = region.split()
    candidates = []
    for name, code in sgg.items():
        n_tokens = name.split()
        # 질의 토큰들이 순서대로 공식 명칭 토큰에 부분일치하면 후보
        i = 0
        for qt in q_tokens:
            while i < len(n_tokens) and qt not in n_tokens[i]:
                i += 1
            if i == len(n_tokens):
                break
            i += 1
        else:
            candidates.append((name, code))

    if len(candidates) == 1:
        return candidates[0][1]
    if not candidates:
        sys.exit(f"법정동코드를 찾을 수 없습니다: '{region}' — "
                 f"config.yaml에 lawd_cd를 직접 지정하세요.")
    names = ", ".join(f"{n}({c})" for n, c in candidates[:8])
    sys.exit(f"'{region}'에 해당하는 시군구가 여러 개입니다: {names} — "
             f"시도명을 포함해 더 구체적으로 쓰거나 lawd_cd를 직접 지정하세요.")
