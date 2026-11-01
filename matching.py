"""관심 단지 매칭 로직 (monitor와 dashboard가 공유).

거래 레코드(rec)가 config의 한 단지(complex_cfg)에 해당하는지 판정한다.
순환 import을 피하기 위해 monitor/dashboard 양쪽에서 import하는 독립 모듈로 둔다.
"""


def match_complex(rec, complex_cfg):
    """거래 1건이 관심 단지 1개와 일치하는지.

    - 지역코드(lawd_cd) 일치
    - 단지명(aptNm)에 match 키워드 중 하나라도 포함
      · 키워드가 '='로 시작하면 정확일치(예: "=현대" → 단지명이 정확히 "현대"일 때만).
        이름이 짧아 부분일치가 다른 단지까지 걸릴 때 사용.
    - areas가 지정됐으면 전용면적 정수 대역이 그 안에 포함
    """
    if str(rec.get("lawd_cd", "")) != str(complex_cfg.get("lawd_cd", "")):
        return False
    apt = rec["apt_nm"]
    if not any(apt == kw[1:] if kw.startswith("=") else kw in apt
               for kw in complex_cfg["match"]):
        return False
    if complex_cfg["areas"] and int(rec["area"]) not in complex_cfg["areas"]:
        return False
    return True


def matching_complex_name(rec, complexes):
    """거래가 매칭되는 첫 단지의 표시 이름. 없으면 None."""
    for c in complexes:
        if match_complex(rec, c):
            return c["name"]
    return None
