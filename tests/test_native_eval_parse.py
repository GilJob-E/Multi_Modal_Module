#!/usr/bin/env python3
"""native_eval JSON 파싱/복구 단위 테스트 — GPU/서버 불필요(순수 함수).

compact tail이 max_tokens 상한에 닿아 JSON이 잘려도 부분 신호라도 건지는지(2026-05-30 실측
회귀: 5키 중첩 스키마가 160토큰에서 잘려 tail 신호 0개였음 → 2키 스키마 + 복구로 교정).
실행: PYTHONPATH=src python3 tests/test_native_eval_parse.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_infer.native_eval import _extract_json, _repair_truncated_json  # noqa: E402


def test_clean_and_fenced():
    assert _extract_json('{"summary": "ok", "critique": ["a", "b"]}') == {"summary": "ok", "critique": ["a", "b"]}
    assert _extract_json('```json\n{"summary": "x", "critique": ["y"]}\n```')["summary"] == "x"
    # 산문에 둘러싸인 object
    assert _extract_json('네, 결과입니다: {"summary": "s"} 끝.')["summary"] == "s"
    print("  ✓ clean / fenced / 산문 둘러싸임 파싱")


def test_truncated_recovered():
    # 문자열 중간 잘림
    assert _extract_json('{"summary": "중간에 잘린 요')["summary"].startswith("중간")
    # 리스트 중간 잘림
    d = _extract_json('{"summary": "ok", "critique": ["약점1", "약점2')
    assert d["summary"] == "ok" and d["critique"][0] == "약점1"
    # 옛 5키 중첩이 잘린 경우도 부분 복구
    d2 = _extract_json('{"verbal": {"note": "논리 약함"}, "vocal": {"note": "단조"}, "visual": {"note": "시선 불안')
    assert "verbal" in d2 and d2["verbal"]["note"] == "논리 약함"
    # "key": 만 있고 값 없이 끊김
    d3 = _extract_json('{"summary": "ok", "critique":')
    assert d3["summary"] == "ok"
    print("  ✓ 잘린 JSON(문자열/리스트/중첩/콜론끝) 복구")


def test_unrecoverable_raises():
    for bad in ("", "그냥 텍스트, JSON 없음", "[1, 2, 3"):
        try:
            _extract_json(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"should raise on {bad!r}")
    assert _repair_truncated_json("no brace here") is None
    print("  ✓ 복구 불가 입력은 ValueError / None")


def main() -> int:
    tests = [test_clean_and_fenced, test_truncated_recovered, test_unrecoverable_raises]
    print(f"=== native_eval parse tests ({len(tests)}) ===")
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"  ✗ {t.__name__}: {e}")
            traceback.print_exc()
    print(f"=== {'ALL PASS' if not failed else f'{failed} FAILED'} ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
