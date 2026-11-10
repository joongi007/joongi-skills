#!/usr/bin/env python3
"""파이썬 `re`의 파국적 백트래킹(ReDoS)을 재현한다.

`(a+)+$` 에 매칭 실패하는 입력을 주면 입력 한 글자마다 소요 시간이 두 배가 된다.
표준 라이브러리만 쓴다.

    python3 measure_backtracking.py            # 20~28자 (약 10초)
    python3 measure_backtracking.py 31         # 20~31자 (약 80초)
"""

import re
import sys
import time

# 중첩 수량자. "a"의 반복을 다시 반복하므로 엔진이 분할 조합을 전부 시도한다.
PATTERN = r"^(a+)+$"

# 매칭이 실패해야 백트래킹이 최대가 된다. 뒤에 붙인 "!"가 그 역할.
SUFFIX = "!"

# 기본 상한 28 — 이 기계에서 합계 약 10초. 형태를 보기에 충분하고 기다릴 만하다.
DEFAULT_MAX_LEN = 28

# 한 번의 매칭이 이 시간을 넘으면 멈춘다. 두 배씩 늘어나므로 다음 줄은 두 배로 걸린다.
STOP_AFTER_SECONDS = 30.0


def main() -> int:
    try:
        max_len = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAX_LEN
    except ValueError:
        print(f"usage: {sys.argv[0]} [max_input_length]", file=sys.stderr)
        return 1

    regex = re.compile(PATTERN)
    print(f"pattern: {PATTERN}   input: 'a' * n + '{SUFFIX}'")
    print(f"python {sys.version.split()[0]}\n")
    print(f"{'input len':>10} {'elapsed (s)':>14}")

    for n in range(20, max_len + 1):
        text = "a" * n + SUFFIX
        start = time.perf_counter()
        regex.search(text)
        elapsed = time.perf_counter() - start
        print(f"{n:>10} {elapsed:>14.4f}")
        if elapsed > STOP_AFTER_SECONDS:
            print(f"\n{elapsed:.1f}s 초과 — 다음 길이는 약 두 배가 걸린다. 여기서 중단.")
            break

    print("\n길이를 자르는 것이 가장 싼 방어다: if len(s) > 256: reject")
    return 0


if __name__ == "__main__":
    sys.exit(main())
