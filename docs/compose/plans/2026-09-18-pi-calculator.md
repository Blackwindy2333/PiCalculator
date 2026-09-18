# π 计算器（Pi Calculator）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个带 PySide6 GUI 的 π 计算小工具：Chudnovsky+二分分裂实时计算、滚动显示已稳定数字、可暂停/保存/续算，结果确定性写入 pi.txt，并具备 SHA-256 / BBP 独立校验。

**Architecture:** 计算内核（gmpy2/GMP）与 GUI 完全分离；GUI 主进程通过两个 `multiprocessing.Queue` 驱动 worker 子进程（唯一的 pi.txt 写入者）；内核以"分块二分分裂 + 运行态 (P,Q,T)"支持任意时刻暂停/检查点；二进制→十进制只在"刷新节流"与完成时刻做，且只写"稳定前缀"。

**Tech Stack:** Python 3.14（64 位）+ gmpy2 2.3.1（GMP）+ PySide6 6.11（Qt 6）+ psutil；pytest 测试。

**Spec:** `docs/compose/specs/2026-09-18-pi-calculator-design.md`（章节锚点 [S1]–[S11] 为验收依据）

## Global Constraints

以下约束对**每一个任务**生效，实施者与评审者默认继承、不得各自变通：

- **提交纪律（用户硬性要求）**：每完成**一个文件**的更改立即单独提交一次 commit；消息格式 `<type>. <具体修改内容>`，`type ∈ {feat., fix., bug., docs., chore., test., perf., refactor.}`。禁止把多个文件的改动合成一个 commit。
- **解释器**：只用 64 位 `py -3.14`；一切执行命令走 `.venv\Scripts\python.exe` 全路径（`where python` 仍会命中 WindowsApps stub，禁止裸 `python`）。
- **镜像源**：pip 安装不得覆盖已配置的清华镜像（不加 `-i` / `--index-url` 等覆盖参数）。
- **数值口径（全项目唯一来源 = `pi_tool/common/constants.py`）**：`DIGITS_PER_TERM = 14.181647462725477`、`GUARD_DIGITS = 20`、`STABLE_MARGIN = 22`、`C3_OVER_24 = 10939058860032000`、`ALGORITHM_ID = "chudnovsky-bs-v1"`。任何模块不得复制这些字面量。
- **pi.txt 字节格式（不变量）**：字符流 = `"3."` + 小数位；**每累计 1000 个流字符后插入 `'\n'`**；完成时若文件未以 `'\n'` 结尾则补一个；纯 ASCII；**只有 worker 子进程可写**。同一 (target_digits, 配置) 必须产生相同字节、相同 SHA-256（与暂停点/分块无关）。
- **稳定位数规则**：只显示/只写盘 `stable_digits_for_terms(k)` 以内的数字；任何路径不得写出可能变化的数字。
- **测试要求**：每个任务先写失败测试（TDD），测试命令一律 `.venv\Scripts\python.exe -m pytest tests -q`；测试不得依赖网络。
- **语言**：GUI 文案、日志、提交信息、README 用中文；代码默认不写注释，仅在算法口径等非显然处写简短中文注释。

---

## 文件结构（创建/修改清单）

| 文件 | 职责 |
|---|---|
| `requirements.txt` / `requirements-dev.txt` | 运行时/开发依赖声明 |
| `.gitignore` | 忽略 `.venv/ output/ settings.json __pycache__/ .pytest_cache/ *.log` |
| `pi_tool/__init__.py` `pi_tool/common/__init__.py` `pi_tool/engine/__init__.py` `pi_tool/app/__init__.py` `tests/__init__.py` `scripts/__init__.py` | 包骨架 |
| `pi_tool/__main__.py` | GUI 入口（freeze_support + 启动主窗口） |
| `pi_tool/common/constants.py` | 数值常量 + 权威 π 常数（100/1000 位十进制、64 位十六进制）+ 项数/稳定位数函数 |
| `pi_tool/common/config.py` | `Config` dataclass + settings.json 读写 + 数值钳制 |
| `pi_tool/common/protocol.py` | 进程间命令/事件 dataclass |
| `pi_tool/engine/chudnovsky.py` | 叶子/合并/二分分裂/分块运行态 `SeriesState` |
| `pi_tool/engine/decimal.py` | 稳定前缀提取（十进制/十六进制，整数化） |
| `pi_tool/engine/checkpoint.py` | 检查点二进制格式（原子写入） |
| `pi_tool/engine/bbp.py` | BBP 公式独立实现（可取消） |
| `pi_tool/engine/verify.py` | 常数比对 / SHA-256 / BBP 交叉校验编排 |
| `pi_tool/engine/worker.py` | 子进程主循环 + 文件写入 + 会话保存 + CLI（供测试与调试） |
| `pi_tool/app/theme.py` | dark/light QSS |
| `pi_tool/app/widgets.py` | 速率/内存面板、数字滚动区、频率条形图、新计算对话框 |
| `pi_tool/app/main_window.py` | 主窗口、状态机、事件轮询、进程生命周期 |
| `pi_tool/app/history.py` | 会话扫描与 recent_outputs 维护 |
| `pi_tool/app/search.py` | mmap 搜索 QThread |
| `pi_tool/app/export.py` | gzip 导出 QThread |
| `scripts/bench.py` | 基准与 LEAF_CUTOFF 校准 |
| `tests/machin_ref.py` | 独立参考算法（Machin），仅测试/常量生成用 |
| `tests/test_constants.py` `test_chudnovsky.py` `test_decimal.py` `test_checkpoint.py` `test_bbp.py` `test_verify.py` `test_config.py` `test_worker_e2e.py` | 自动化测试 |
| `run.bat` / `README.md` | 一键启动与文档 |

---

### Task 1: 环境与项目骨架

**Covers:** [S9]

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `pi_tool/__init__.py`, `pi_tool/__main__.py`, `pi_tool/common/__init__.py`, `pi_tool/engine/__init__.py`, `pi_tool/app/__init__.py`, `tests/__init__.py`, `scripts/__init__.py`

**Interfaces:**
- Consumes: 无
- Produces: 可用的 `.venv`（含 gmpy2/PySide6/psutil/pytest）；`python -m pi_tool` 可启动（GUI 在 Task 11 前会因缺 main_window 报错，属预期，冒烟只验证 `import pi_tool`）

- [ ] **Step 1: 创建 venv 并安装依赖**

运行：
```
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install gmpy2 PySide6 psutil pytest
```
预期：`Successfully installed gmpy2-2.3.1 PySide6-6.11.x psutil-7.x pytest-8.x`（全部来自清华镜像的 wheel，无编译过程）。

- [ ] **Step 2: 验证关键库可导入且为 64 位**

运行：
```
.venv\Scripts\python.exe -c "import sys, gmpy2, psutil; import PySide6; print(sys.maxsize > 2**32, gmpy2.version(), psutil.__version__, PySide6.__version__)"
```
预期输出：`True 2.3.1 7.x.x 6.11.x`。

- [ ] **Step 3: 写 requirements.txt 并提交**

```text
gmpy2>=2.3.1
PySide6>=6.11.2
psutil>=7.0.0
```
```
git add requirements.txt
git commit -m "chore. 添加运行时依赖清单（gmpy2/PySide6/psutil）"
```

- [ ] **Step 4: 写 requirements-dev.txt 并提交**

```text
pytest>=8.0.0
```
```
git add requirements-dev.txt
git commit -m "chore. 添加开发依赖清单（pytest）"
```

- [ ] **Step 5: 写 .gitignore 并提交**

```text
.venv/
__pycache__/
*.pyc
.pytest_cache/
output/
settings.json
*.log
```
```
git add .gitignore
git commit -m "chore. 忽略虚拟环境/运行产物/本地配置"
```

- [ ] **Step 6: 写包骨架（6 个 `__init__.py`），逐文件提交**

`pi_tool/__init__.py`：
```python
__version__ = "0.1.0"
```
`pi_tool/common/__init__.py`、`pi_tool/engine/__init__.py`、`pi_tool/app/__init__.py`、`tests/__init__.py`、`scripts/__init__.py` 均为空文件。

逐个提交（示例）：
```
git add pi_tool/__init__.py
git commit -m "chore. 添加 pi_tool 包版本声明"
git add pi_tool/common/__init__.py
git commit -m "chore. 添加 common 子包骨架"
git add pi_tool/engine/__init__.py
git commit -m "chore. 添加 engine 子包骨架"
git add pi_tool/app/__init__.py
git commit -m "chore. 添加 app 子包骨架"
git add tests/__init__.py
git commit -m "chore. 添加 tests 包骨架"
git add scripts/__init__.py
git commit -m "chore. 添加 scripts 包骨架"
```

- [ ] **Step 7: 写 GUI 入口 `pi_tool/__main__.py` 并提交**

```python
from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()
    from pi_tool.app.main_window import run_app

    return run_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
```
```
git add pi_tool/__main__.py
git commit -m "feat. 添加 GUI 入口（freeze_support + 惰性加载主窗口）"
```

- [ ] **Step 8: 冒烟验证**

运行：
```
.venv\Scripts\python.exe -c "import pi_tool; print(pi_tool.__version__)"
```
预期输出：`0.1.0`。

---

### Task 2: 数值常量与独立参考算法

**Covers:** [S4], [S8]

**Files:**
- Create: `pi_tool/common/constants.py`, `tests/machin_ref.py`, `tests/test_constants.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `constants.ALGORITHM_ID: str`、`DIGITS_PER_TERM: float`、`GUARD_DIGITS: int`、`STABLE_MARGIN: int`、`LEAF_CUTOFF_INITIAL: int`、`C3_OVER_24: int`
  - `constants.PI_FIRST_100: str`（无 "3." 的 100 位）、`PI_FIRST_1000: str`（1000 位）、`PI_HEX_FIRST_64: str`（64 位大写十六进制）
  - `constants.terms_for_digits(digits: int) -> int`、`constants.stable_digits_for_terms(terms: int) -> int`
  - `tests.machin_ref.pi_digits_machin(digits: int) -> str`（返回 `"3" + digits 位`）

- [ ] **Step 1: 写失败测试 `tests/test_constants.py`**

```python
import math

from pi_tool.common.constants import (
    PI_FIRST_100,
    PI_FIRST_1000,
    PI_HEX_FIRST_64,
    DIGITS_PER_TERM,
    stable_digits_for_terms,
    terms_for_digits,
)
from tests.machin_ref import pi_digits_machin


def test_first_100_matches_canonical_value():
    assert PI_FIRST_100 == pi_digits_machin(100)[1:]
    assert PI_FIRST_100.startswith(format(math.pi, ".16f")[2:])


def test_first_1000_frozen_from_independent_algorithm():
    assert PI_FIRST_1000 == pi_digits_machin(1000)[1:]
    assert PI_FIRST_1000.startswith(PI_FIRST_100)


def test_hex_constant_shape():
    assert len(PI_HEX_FIRST_64) == 64
    assert set(PI_HEX_FIRST_64) <= set("0123456789ABCDEF")


def test_terms_and_stable_invariants():
    assert terms_for_digits(1000) >= 1000 / DIGITS_PER_TERM
    assert stable_digits_for_terms(0) == 0
    previous = -1
    for terms in range(0, 1000, 37):
        current = stable_digits_for_terms(terms)
        assert current >= previous
        previous = current
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_constants.py -q`
预期：FAIL，`ModuleNotFoundError: No module named 'pi_tool.common.constants'`。

- [ ] **Step 3: 写 `tests/machin_ref.py`**

```python
from __future__ import annotations

import sys


def arctan_inv(x: int, scale: int) -> int:
    """floor(arctan(1/x) * scale)，独立于 Chudnovsky 的参考算法。"""
    total = 0
    x_squared = x * x
    power = x
    k = 0
    while True:
        term = scale // (power * (2 * k + 1))
        if term == 0:
            break
        total += -term if k & 1 else term
        power *= x_squared
        k += 1
    return total


def pi_digits_machin(digits: int) -> str:
    """Machin 公式：π = 16·arctan(1/5) − 4·arctan(1/239)，返回 '3' + digits 位。"""
    guard = 30
    scale = 10 ** (digits + guard)
    value = 16 * arctan_inv(5, scale) - 4 * arctan_inv(239, scale)
    return str(value)[: digits + 1]


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    print(pi_digits_machin(count))
```
```
git add tests/machin_ref.py
git commit -m "test. 添加 Machin 公式独立参考实现（常量生成与交叉验证用）"
```

- [ ] **Step 4: 写 `pi_tool/common/constants.py`（PI_FIRST_1000 由下一步生成后填入）**

```python
from __future__ import annotations

ALGORITHM_ID = "chudnovsky-bs-v1"

DIGITS_PER_TERM = 14.181647462725477
GUARD_DIGITS = 20
STABLE_MARGIN = 22
LEAF_CUTOFF_INITIAL = 32
C3_OVER_24 = 10939058860032000

PI_FIRST_100 = (
    "14159265358979323846264338327950288419716939937510582097494459230781640628"
    "62089986280348253421170679"
)

PI_FIRST_1000 = (
    ""
)

PI_HEX_FIRST_64 = "243F6A8885A308D313198A2E03707344A4093822299F31D0082EFA98EC4E6C89"


def terms_for_digits(digits: int) -> int:
    return int((digits + GUARD_DIGITS) / DIGITS_PER_TERM) + 3


def stable_digits_for_terms(terms: int) -> int:
    return max(0, int(DIGITS_PER_TERM * terms) - STABLE_MARGIN)
```

- [ ] **Step 5: 生成并填入 PI_FIRST_1000**

运行：
```
.venv\Scripts\python.exe -m tests.machin_ref 1000
```
把输出的 1001 个字符去掉首位 `3` 后的 1000 位粘贴为 `PI_FIRST_1000` 的值（按每行 76 个字符切成相邻字符串字面量）。填完后 `Step 1` 的 `test_first_100_matches_canonical_value` 同时充当对 `PI_FIRST_100`（人工录入）与 Machin 实现的互证。
```
git add pi_tool/common/constants.py
git commit -m "feat. 添加数值常量与权威 π 常数（100/1000 位十进制 + 64 位十六进制）"
```

- [ ] **Step 6: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_constants.py -q`
预期：`4 passed`。

---

### Task 3: 二分分裂内核

**Covers:** [S4]

**Files:**
- Create: `pi_tool/engine/chudnovsky.py`, `tests/test_chudnovsky.py`

**Interfaces:**
- Consumes: `constants`（Task 2）
- Produces:
  - `Triple(p: mpz, q: mpz, t: mpz)`（frozen dataclass）
  - `merge(left: Triple, right: Triple) -> Triple`
  - `bs(a: int, b: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> Triple`（精确覆盖项区间 `[a, b)`）
  - `SeriesState`：字段 `terms: int`、`triple: Triple`；方法 `extend(extra_terms: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> None`（幂等安全：`extra_terms <= 0` 时不动）
  - 语义恒等式（供后续所有模块依赖）：`T/Q = Σ_{k<a}^{b} (−1)^k(6k)!(13591409+545140134k) / ((3k)!(k!)^3·640320^{3k})`，且 `π = 426880·√10005·Q/T`

- [ ] **Step 1: 写失败测试 `tests/test_chudnovsky.py`**

```python
import math
from fractions import Fraction

import pytest

from pi_tool.common.constants import DIGITS_PER_TERM, stable_digits_for_terms, terms_for_digits
from pi_tool.engine.chudnovsky import SeriesState, bs


def _naive_sum(terms: int) -> Fraction:
    total = Fraction(0)
    for k in range(terms):
        term = Fraction(
            math.factorial(6 * k) * (13591409 + 545140134 * k),
            math.factorial(3 * k) * math.factorial(k) ** 3 * 640320 ** (3 * k),
        )
        total += -term if k & 1 else term
    return total


@pytest.mark.parametrize("terms", [1, 2, 3, 7, 16, 50])
def test_binary_splitting_matches_naive_sum(terms):
    state = SeriesState()
    state.extend(terms, leaf_cutoff=1)
    assert Fraction(state.triple.t, state.triple.q) == _naive_sum(terms)


def test_leaf_cutoff_does_not_change_result():
    fast = bs(0, 200, leaf_cutoff=32)
    slow = bs(0, 200, leaf_cutoff=1)
    assert (fast.p, fast.q, fast.t) == (slow.p, slow.q, slow.t)


def test_chunked_state_equals_single_shot():
    state = SeriesState()
    for step in (-5, 0, 1, 5, 39, 155):
        state.extend(step)
    reference = bs(0, 200)
    assert state.terms == 200
    assert (state.triple.p, state.triple.q, state.triple.t) == (reference.p, reference.q, reference.t)


def test_terms_and_stable_monotonic():
    assert terms_for_digits(10000) == int((10000 + 20) / DIGITS_PER_TERM) + 3
    previous = -1
    for terms in range(0, 1000, 37):
        current = stable_digits_for_terms(terms)
        assert current >= previous
        previous = current
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_chudnovsky.py -q`
预期：FAIL，`ModuleNotFoundError: No module named 'pi_tool.engine.chudnovsky'`。

- [ ] **Step 3: 写 `pi_tool/engine/chudnovsky.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from gmpy2 import mpz

from ..common.constants import (
    C3_OVER_24,
    DIGITS_PER_TERM,
    GUARD_DIGITS,
    LEAF_CUTOFF_INITIAL,
    STABLE_MARGIN,
    stable_digits_for_terms,
    terms_for_digits,
)


@dataclass(frozen=True)
class Triple:
    p: mpz
    q: mpz
    t: mpz


def _leaf(a: int) -> Triple:
    if a == 0:
        p = q = mpz(1)
    else:
        p = mpz(6 * a - 5) * (2 * a - 1) * (6 * a - 1)
        q = mpz(a) ** 3 * C3_OVER_24
    t = p * (13591409 + 545140134 * a)
    if a & 1:
        t = -t
    return Triple(p, q, t)


def _leaf_range(a: int, b: int) -> Triple:
    node = _leaf(a)
    for k in range(a + 1, b):
        child = _leaf(k)
        node = Triple(
            node.p * child.p,
            node.q * child.q,
            node.t * child.q + node.p * child.t,
        )
    return node


def merge(left: Triple, right: Triple) -> Triple:
    return Triple(
        left.p * right.p,
        left.q * right.q,
        left.t * right.q + left.p * right.t,
    )


def bs(a: int, b: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> Triple:
    if b - a <= leaf_cutoff:
        return _leaf_range(a, b)
    middle = (a + b) // 2
    return merge(bs(a, middle, leaf_cutoff), bs(middle, b, leaf_cutoff))


class SeriesState:
    """项区间 [0, terms) 的运行态：π = 426880·√10005·Q/T。"""

    def __init__(self) -> None:
        self.terms = 0
        self.triple = Triple(mpz(1), mpz(1), mpz(0))

    def extend(self, extra_terms: int, leaf_cutoff: int = LEAF_CUTOFF_INITIAL) -> None:
        if extra_terms <= 0:
            return
        chunk = bs(self.terms, self.terms + extra_terms, leaf_cutoff)
        self.triple = merge(self.triple, chunk)
        self.terms += extra_terms


__all__ = [
    "Triple",
    "SeriesState",
    "bs",
    "merge",
    "stable_digits_for_terms",
    "terms_for_digits",
]
```

- [ ] **Step 4: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_chudnovsky.py -q`
预期：`10 passed`（6 个参数化用例 + 4 个独立用例）。

- [ ] **Step 5: 提交**

```
git add pi_tool/engine/chudnovsky.py
git commit -m "feat. 实现 Chudnovsky 二分分裂内核与分块运行态"
git add tests/test_chudnovsky.py
git commit -m "test. 添加内核对照测试（朴素求和/叶阈值无关/分块一致性）"
```

---

### Task 4: 稳定前缀提取（十进制/十六进制）

**Covers:** [S4]

**Files:**
- Create: `pi_tool/engine/decimal.py`, `tests/test_decimal.py`

**Interfaces:**
- Consumes: `SeriesState`（Task 3）、`GUARD_DIGITS`/`stable_digits_for_terms`（Task 2）
- Produces:
  - `NotEnoughTerms(Exception)`
  - `pi_prefix_decimal(state: SeriesState, digits: int) -> str`（返回**小数位**字符串，长度恰为 `digits`，不含 `"3."`；稳定位数不足时抛 `NotEnoughTerms`）
  - `pi_prefix_hex(state: SeriesState, hex_digits: int) -> str`（大写十六进制小数位，长度恰为 `hex_digits`）
  - 关键不变量：同一 π 状态下手动请求不同的 `digits`，得到的前缀互为前缀（已写出的数字永不改变）

- [ ] **Step 1: 写失败测试 `tests/test_decimal.py`**

```python
import pytest

from pi_tool.common.constants import PI_FIRST_1000, PI_HEX_FIRST_64
from pi_tool.engine.chudnovsky import SeriesState, terms_for_digits
from pi_tool.engine.decimal import NotEnoughTerms, pi_prefix_decimal, pi_prefix_hex


def _state_for(digits: int) -> SeriesState:
    state = SeriesState()
    state.extend(terms_for_digits(digits))
    return state


def test_prefix_1000_matches_frozen_constant():
    assert pi_prefix_decimal(_state_for(1000), 1000) == PI_FIRST_1000


def test_prefix_10000_extends_1000():
    assert pi_prefix_decimal(_state_for(10_000), 10_000).startswith(PI_FIRST_1000)


def test_prefix_is_stable_across_requested_lengths():
    state = _state_for(3000)
    assert pi_prefix_decimal(state, 2000).startswith(pi_prefix_decimal(state, 1000))


def test_prefix_independent_of_state_progress():
    assert pi_prefix_decimal(_state_for(2000), 1000) == pi_prefix_decimal(_state_for(5000), 1000)


def test_hex_prefix_matches_constant():
    assert pi_prefix_hex(_state_for(1000), 64) == PI_HEX_FIRST_64


def test_raises_when_not_enough_terms():
    state = SeriesState()
    state.extend(1)
    with pytest.raises(NotEnoughTerms):
        pi_prefix_decimal(state, 1000)
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_decimal.py -q`
预期：FAIL，`ModuleNotFoundError: No module named 'pi_tool.engine.decimal'`。

- [ ] **Step 3: 写 `pi_tool/engine/decimal.py`**

```python
from __future__ import annotations

import gmpy2
from gmpy2 import mpz

from ..common.constants import GUARD_DIGITS, stable_digits_for_terms
from .chudnovsky import SeriesState

HEX_TO_DECIMAL_RATIO = 1.20412


class NotEnoughTerms(Exception):
    """稳定位数不足，无法提取指定长度的前缀。"""


def _require_stable(state: SeriesState, digits: int) -> None:
    stable = stable_digits_for_terms(state.terms)
    if stable < digits:
        raise NotEnoughTerms(f"稳定位数 {stable} < 需要 {digits}")


def pi_prefix_decimal(state: SeriesState, digits: int) -> str:
    _require_stable(state, digits)
    m = digits + GUARD_DIGITS
    root = gmpy2.isqrt(mpz(10005) * mpz(10) ** (2 * m))
    value = (426880 * root * state.triple.q) // state.triple.t
    return str(value)[1 : 1 + digits]


def pi_prefix_hex(state: SeriesState, hex_digits: int) -> str:
    _require_stable(state, int(hex_digits * HEX_TO_DECIMAL_RATIO) + 8)
    h = hex_digits + 12
    root = gmpy2.isqrt(mpz(10005) * mpz(16) ** (2 * h))
    value = (426880 * root * state.triple.q) // state.triple.t
    return _mpz_to_base16(value)[1 : 1 + hex_digits]


def _mpz_to_base16(value: mpz) -> str:
    try:
        return value.digits(16).upper()
    except AttributeError:
        pass
    try:
        return gmpy2.digits(value, 16).upper()
    except AttributeError:
        return format(int(value), "X")
```

- [ ] **Step 4: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_decimal.py -q`
预期：`6 passed`。
若 `test_hex_prefix_matches_constant` 失败且错误来自 `_mpz_to_base16` 的 API 不存在，按退化路径实测 `gmpy2.digits` 的真实签名并修正实现（测试必须保持六个全绿，三个分支任选其一以测试通过为准）。

- [ ] **Step 5: 提交**

```
git add pi_tool/engine/decimal.py
git commit -m "feat. 实现稳定前缀整数化提取（十进制/十六进制）"
git add tests/test_decimal.py
git commit -m "test. 添加前缀提取与稳定性测试"
```

---

### Task 5: 基准校准（LEAF_CUTOFF 固化）

**Covers:** [S2], [S10]

**Files:**
- Create: `scripts/bench.py`
- Modify: `pi_tool/common/constants.py`（仅当校准结果 ≠ 32 时）

**Interfaces:**
- Consumes: `SeriesState`（Task 3）、`pi_prefix_decimal`（Task 4）
- Produces: 实测性能表（Task 13 写入 README）；可能修改后的 `LEAF_CUTOFF_INITIAL`

- [ ] **Step 1: 写 `scripts/bench.py` 并提交**

```python
from __future__ import annotations

import time

from pi_tool.engine.chudnovsky import SeriesState, terms_for_digits
from pi_tool.engine.decimal import pi_prefix_decimal


def measure(digits: int, leaf_cutoff: int) -> tuple[float, float]:
    terms = terms_for_digits(digits)
    state = SeriesState()
    started = time.perf_counter()
    state.extend(terms, leaf_cutoff=leaf_cutoff)
    split_seconds = time.perf_counter() - started
    started = time.perf_counter()
    pi_prefix_decimal(state, digits)
    extract_seconds = time.perf_counter() - started
    return split_seconds, extract_seconds


def main() -> None:
    print(f"{'digits':>12} {'leaf':>5} {'split_s':>10} {'extract_s':>10}")
    for digits in (10_000, 100_000, 1_000_000):
        for leaf_cutoff in (1, 8, 32, 128):
            split_seconds, extract_seconds = measure(digits, leaf_cutoff)
            print(f"{digits:>12,} {leaf_cutoff:>5} {split_seconds:>10.3f} {extract_seconds:>10.3f}")


if __name__ == "__main__":
    main()
```
```
git add scripts/bench.py
git commit -m "feat. 添加基准脚本（规模×叶阈值耗时矩阵）"
```

- [ ] **Step 2: 运行基准并记录结果**

运行：`.venv\Scripts\python.exe -m scripts.bench`
预期：12 行表格；1,000,000 位行中 `split_s` 与 `extract_s` 为秒级到几十秒级。**把整张表复制保存**（Task 13 写入 README）。

- [ ] **Step 3: 依据 1,000,000 位那一组的 `split_s` 选择最优 `leaf_cutoff`**

- 若最优值就是 32：本任务不做代码改动，只保留 Step 1 的那一次提交。
- 若不同：把 `pi_tool/common/constants.py` 中的 `LEAF_CUTOFF_INITIAL` 改为该值，运行 `.venv\Scripts\python.exe -m pytest tests -q` 确认全绿（该参数只影响速度，任何测试变红都说明改错了），然后：
```
git add pi_tool/common/constants.py
git commit -m "perf. 依据基准将 LEAF_CUTOFF_INITIAL 校准为 <值>"
```

---

### Task 6: 检查点二进制格式

**Covers:** [S5], [S11]

**Files:**
- Create: `pi_tool/engine/checkpoint.py`, `tests/test_checkpoint.py`

**Interfaces:**
- Consumes: `SeriesState`/`Triple`（Task 3）
- Produces:
  - `MAGIC = b"PICK1"`、`VERSION = 1`
  - `CheckpointError(Exception)`
  - `Checkpoint(terms: int, stable_digits: int, triple: Triple, config: dict)`（frozen dataclass）
  - `save(path: Path, state: SeriesState, stable_digits: int, config: dict) -> None`（先写 `.tmp` + `fsync` + `os.replace` 原子替换）
  - `load(path: Path, expected: dict) -> Checkpoint`（magic/版本/口径快照任一不符 → `CheckpointError`；文件截断 → `CheckpointError`）
  - 口径快照键约定（save 与 load 双方必用）：`algorithm`、`target_digits`、`digits_per_term`、`guard_digits`、`stable_margin`

- [ ] **Step 1: 写失败测试 `tests/test_checkpoint.py`**

```python
import pytest

from pi_tool.common.constants import ALGORITHM_ID, DIGITS_PER_TERM, GUARD_DIGITS, STABLE_MARGIN
from pi_tool.engine import checkpoint
from pi_tool.engine.chudnovsky import SeriesState


def _snapshot(target_digits: int = 100_000) -> dict:
    return {
        "algorithm": ALGORITHM_ID,
        "target_digits": target_digits,
        "digits_per_term": DIGITS_PER_TERM,
        "guard_digits": GUARD_DIGITS,
        "stable_margin": STABLE_MARGIN,
    }


def test_roundtrip(tmp_path):
    state = SeriesState()
    state.extend(123)
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, state, stable_digits=1500, config=_snapshot())
    loaded = checkpoint.load(path, _snapshot())
    assert loaded.terms == 123
    assert loaded.stable_digits == 1500
    assert (loaded.triple.p, loaded.triple.q, loaded.triple.t) == (
        state.triple.p,
        state.triple.q,
        state.triple.t,
    )


def test_rejects_bad_magic(tmp_path):
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, SeriesState(), stable_digits=0, config=_snapshot())
    raw = bytearray(path.read_bytes())
    raw[0] = ord("X")
    path.write_bytes(raw)
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.load(path, _snapshot())


def test_rejects_truncated_file(tmp_path):
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, SeriesState(), stable_digits=0, config=_snapshot())
    path.write_bytes(path.read_bytes()[:32])
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.load(path, _snapshot())


def test_rejects_snapshot_mismatch(tmp_path):
    path = tmp_path / "pi.checkpoint.bin"
    checkpoint.save(path, SeriesState(), stable_digits=0, config=_snapshot(100_000))
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.load(path, _snapshot(200_000))
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_checkpoint.py -q`
预期：FAIL，`ModuleNotFoundError: No module named 'pi_tool.engine.checkpoint'`。

- [ ] **Step 3: 写 `pi_tool/engine/checkpoint.py`**

```python
from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from gmpy2 import mpz

from .chudnovsky import SeriesState, Triple

MAGIC = b"PICK1"
VERSION = 1


class CheckpointError(Exception):
    pass


@dataclass(frozen=True)
class Checkpoint:
    terms: int
    stable_digits: int
    triple: Triple
    config: dict


def _read_exact(handle: BinaryIO, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        block = handle.read(remaining)
        if not block:
            raise CheckpointError("检查点文件被截断")
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def _mpz_to_raw(value: mpz) -> bytes:
    length = (value.bit_length() + 7) // 8
    if length == 0:
        return b""
    try:
        return value.to_bytes(length, "big")
    except AttributeError:
        return int(value).to_bytes(length, "big")


def _raw_to_mpz(raw: bytes) -> mpz:
    if not raw:
        return mpz(0)
    return mpz(int.from_bytes(raw, "big"))


def _write_mpz(handle: BinaryIO, value: mpz) -> None:
    raw = _mpz_to_raw(value)
    handle.write(struct.pack("<Q", len(raw)))
    handle.write(raw)


def _read_mpz(handle: BinaryIO) -> mpz:
    (length,) = struct.unpack("<Q", _read_exact(handle, 8))
    return _raw_to_mpz(_read_exact(handle, length))


def save(path: Path, state: SeriesState, stable_digits: int, config: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(MAGIC)
        handle.write(struct.pack("<IQQ", VERSION, state.terms, stable_digits))
        _write_mpz(handle, state.triple.p)
        _write_mpz(handle, state.triple.q)
        _write_mpz(handle, state.triple.t)
        raw_config = json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")
        handle.write(struct.pack("<I", len(raw_config)))
        handle.write(raw_config)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load(path: Path, expected: dict) -> Checkpoint:
    with open(path, "rb") as handle:
        if _read_exact(handle, len(MAGIC)) != MAGIC:
            raise CheckpointError("检查点 magic 不匹配")
        version, terms, stable_digits = struct.unpack("<IQQ", _read_exact(handle, 20))
        if version != VERSION:
            raise CheckpointError(f"检查点版本不支持: {version}")
        triple = Triple(_read_mpz(handle), _read_mpz(handle), _read_mpz(handle))
        (config_length,) = struct.unpack("<I", _read_exact(handle, 4))
        config = json.loads(_read_exact(handle, config_length).decode("utf-8"))
    for key, value in expected.items():
        if config.get(key) != value:
            raise CheckpointError(f"检查点口径不一致: {key}")
    return Checkpoint(terms, stable_digits, triple, config)
```

- [ ] **Step 4: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_checkpoint.py -q`
预期：`4 passed`。

- [ ] **Step 5: 提交**

```
git add pi_tool/engine/checkpoint.py
git commit -m "feat. 实现检查点二进制格式（原子写入 + 口径快照校验）"
git add tests/test_checkpoint.py
git commit -m "test. 添加检查点往返/损坏/口径不符测试"
```

---

### Task 7: BBP 独立实现

**Covers:** [S8]

**Files:**
- Create: `pi_tool/engine/bbp.py`, `tests/test_bbp.py`

**Interfaces:**
- Consumes: `PI_HEX_FIRST_64`（Task 2）、`SeriesState`/`pi_prefix_hex`（Task 3/4，仅测试用）
- Produces: `bbp_hex_digits(position: int, count: int) -> str`——直接计算 π 小数十六进制第 `position` 位（0 起）起的 `count` 位，返回**大写**串；与引擎实现完全独立（不同公式、不同代码路径）

- [ ] **Step 1: 写失败测试 `tests/test_bbp.py`**

```python
from pi_tool.common.constants import PI_HEX_FIRST_64
from pi_tool.engine.bbp import bbp_hex_digits
from pi_tool.engine.chudnovsky import SeriesState, terms_for_digits
from pi_tool.engine.decimal import pi_prefix_hex


def test_matches_known_constant():
    assert bbp_hex_digits(0, 64) == PI_HEX_FIRST_64
    assert bbp_hex_digits(10, 16) == PI_HEX_FIRST_64[10:26]


def test_cross_check_with_engine_at_position_1000():
    state = SeriesState()
    state.extend(terms_for_digits(5000))
    engine_window = pi_prefix_hex(state, 1016)[1000:1016]
    assert bbp_hex_digits(1000, 16) == engine_window
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_bbp.py -q`
预期：FAIL，`ModuleNotFoundError: No module named 'pi_tool.engine.bbp'`。

- [ ] **Step 3: 写 `pi_tool/engine/bbp.py`**

```python
from __future__ import annotations

from gmpy2 import mpz

COEFFICIENTS = ((1, 4), (4, -2), (5, -1), (6, -1))


def bbp_hex_digits(position: int, count: int) -> str:
    """BBP 公式直接给出 π 小数的十六进制第 position 位起的 count 位（position 从 0 起）。"""
    if position < 0 or count <= 0:
        raise ValueError("position 必须 ≥ 0，count 必须 > 0")
    precision = 4 * (count + 8)
    scale = mpz(1) << precision
    total = mpz(0)
    for j, coefficient in COEFFICIENTS:
        series = mpz(0)
        for k in range(position + 1):
            denominator = 8 * k + j
            residue = pow(16, position - k, denominator)
            series += (mpz(residue) << precision) // denominator
        for k in range(position + 1, position + count + 9):
            denominator = 8 * k + j
            series += scale // (mpz(16) ** (k - position) * denominator)
        total += coefficient * series
    fraction = total & (scale - 1)
    window = (fraction << (4 * count)) // scale
    return format(int(window), f"0{count}X")
```

- [ ] **Step 4: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_bbp.py -q`
预期：`2 passed`。

- [ ] **Step 5: 提交**

```
git add pi_tool/engine/bbp.py
git commit -m "feat. 实现 BBP 十六进制独立提取（交叉校验用）"
git add tests/test_bbp.py
git commit -m "test. 添加 BBP 常数对照与引擎交叉验证测试"
```

---

### Task 8: 校验编排（常数比对 / SHA-256 / 交叉校验）

**Covers:** [S8]

**Files:**
- Create: `pi_tool/engine/verify.py`, `tests/test_verify.py`

**Interfaces:**
- Consumes: `bbp_hex_digits`（Task 7）、`SeriesState`/`pi_prefix_hex`（Task 3/4）
- Produces:
  - `prefix_matches(computed: str, reference: str) -> bool`
  - `sha256_file(path: Path, chunk_size: int = 1 << 20) -> str`（流式，1 GB 文件内存友好）
  - `bbp_crosscheck(state: SeriesState, position: int, count: int) -> tuple[str, str, bool]`（`(expected, got, ok)`；引擎位数不足时透传 `NotEnoughTerms`）

- [ ] **Step 1: 写失败测试 `tests/test_verify.py`**

```python
import hashlib

import pytest

from pi_tool.common.constants import PI_HEX_FIRST_64
from pi_tool.engine.chudnovsky import SeriesState, terms_for_digits
from pi_tool.engine.decimal import NotEnoughTerms
from pi_tool.engine.verify import bbp_crosscheck, prefix_matches, sha256_file

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_matches_known_value(tmp_path):
    path = tmp_path / "abc.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == ABC_SHA256


def test_prefix_matches():
    assert prefix_matches("3141592653", "31415")
    assert not prefix_matches("3141592653", "31416")


def test_bbp_crosscheck_ok():
    state = SeriesState()
    state.extend(terms_for_digits(5000))
    expected, got, ok = bbp_crosscheck(state, 0, 64)
    assert ok
    assert expected == got == PI_HEX_FIRST_64


def test_bbp_crosscheck_raises_when_behind():
    state = SeriesState()
    state.extend(10)
    with pytest.raises(NotEnoughTerms):
        bbp_crosscheck(state, 1000, 16)
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_verify.py -q`
预期：FAIL，`ModuleNotFoundError: No module named 'pi_tool.engine.verify'`。

- [ ] **Step 3: 写 `pi_tool/engine/verify.py`**

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from .bbp import bbp_hex_digits
from .chudnovsky import SeriesState
from .decimal import pi_prefix_hex


def prefix_matches(computed: str, reference: str) -> bool:
    return computed.startswith(reference)


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def bbp_crosscheck(state: SeriesState, position: int, count: int) -> tuple[str, str, bool]:
    expected = bbp_hex_digits(position, count)
    window = pi_prefix_hex(state, position + count)
    got = window[position : position + count]
    return expected, got, expected == got
```

- [ ] **Step 4: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_verify.py -q`
预期：`4 passed`。

- [ ] **Step 5: 提交**

```
git add pi_tool/engine/verify.py
git commit -m "feat. 实现校验编排（常数比对/流式 SHA-256/BBP 交叉校验）"
git add tests/test_verify.py
git commit -m "test. 添加校验模块测试"
```

---

### Task 9: 配置与进程间协议

**Covers:** [S6], [S7]

**Files:**
- Create: `pi_tool/common/config.py`, `pi_tool/common/protocol.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `Config`（dataclass，字段与 spec [S7] settings.json 一一对应：`theme, output_dir, target_digits, refresh_interval_s, autosave_interval_s, memory_limit_gb, view_keep_chars, rate_unit, bbp_default_hex_position, bbp_default_count, recent_outputs`）
  - `sanitize(config: Config) -> Config`（钳制：target∈[1000, 1e11]、refresh≥0.1、autosave≥10、memory≥0.5、view_keep≥10000、bbp_count∈[1,64]、recent_outputs≤20、theme∈{dark,light}、rate_unit∈{s,m}）
  - `load_settings(path) -> Config`（缺失/损坏 → 默认值）、`save_settings(path, config) -> None`（原子写）
  - 命令 dataclass：`PauseCommand`、`ResumeRunCommand`、`SaveCommand`、`StopCommand`、`BbpCheckCommand(position, count)`、`UpdateSettingsCommand(refresh_interval_s, autosave_interval_s, memory_limit_bytes)`
  - 事件 dataclass：`ProgressEvent(terms_done, stable_digits, written_digits, rate_digits_per_s, eta_seconds, mem_bytes, chunk_text)`、`PausedEvent(reason, written_digits)`、`SavedEvent(path, written_digits)`、`DoneEvent(total_digits, sha256)`、`BbpResultEvent(position, count, expected, got, ok)`、`ErrorEvent(message)`、`LogEvent(level, message)`
  - 约定：worker 的**启动参数**（输出目录/目标位数/阈值/resume 标志）经进程参数传递，**不走命令队列**（Windows spawn 语义下最稳）；队列只承载运行中命令

- [ ] **Step 1: 写失败测试 `tests/test_config.py`**

```python
import pickle

from pi_tool.common import protocol
from pi_tool.common.config import Config, load_settings, sanitize, save_settings


def test_config_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    config = Config(target_digits=1234, theme="light", recent_outputs=["a", "b"])
    save_settings(path, config)
    assert load_settings(path) == config


def test_load_missing_or_broken_file_returns_defaults(tmp_path):
    assert load_settings(tmp_path / "nope.json") == Config()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_settings(broken) == Config()


def test_sanitize_clamps_values():
    clean = sanitize(
        Config(
            refresh_interval_s=0.0,
            autosave_interval_s=1,
            memory_limit_gb=0.1,
            view_keep_chars=10,
            target_digits=-5,
            theme="weird",
            rate_unit="x",
            bbp_default_count=999,
            recent_outputs=[str(index) for index in range(50)],
        )
    )
    assert clean.refresh_interval_s >= 0.1
    assert clean.autosave_interval_s >= 10
    assert clean.memory_limit_gb >= 0.5
    assert clean.view_keep_chars >= 10_000
    assert clean.target_digits == 1_000
    assert clean.theme == "dark"
    assert clean.rate_unit == "s"
    assert clean.bbp_default_count == 64
    assert len(clean.recent_outputs) == 20


def test_sanitize_bounds_target_upper():
    assert sanitize(Config(target_digits=10**15)).target_digits == 100_000_000_000


def test_protocol_pickle_roundtrip():
    instances = [
        protocol.PauseCommand(),
        protocol.ResumeRunCommand(),
        protocol.SaveCommand(),
        protocol.StopCommand(),
        protocol.BbpCheckCommand(position=10, count=16),
        protocol.UpdateSettingsCommand(refresh_interval_s=1.0, autosave_interval_s=300.0, memory_limit_bytes=1),
        protocol.ProgressEvent(
            terms_done=1,
            stable_digits=2,
            written_digits=3,
            rate_digits_per_s=4.0,
            eta_seconds=None,
            mem_bytes=5,
            chunk_text="6",
        ),
        protocol.PausedEvent(reason="user", written_digits=7),
        protocol.SavedEvent(path="p", written_digits=8),
        protocol.DoneEvent(total_digits=9, sha256="a" * 64),
        protocol.BbpResultEvent(position=1, count=16, expected="A", got="A", ok=True),
        protocol.ErrorEvent(message="x"),
        protocol.LogEvent(level="info", message="y"),
    ]
    for item in instances:
        assert pickle.loads(pickle.dumps(item)) == item
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_config.py -q`
预期：FAIL，`ModuleNotFoundError: No module named 'pi_tool.common.config'`。

- [ ] **Step 3: 写 `pi_tool/common/config.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

TARGET_DIGITS_MIN = 1_000
TARGET_DIGITS_MAX = 100_000_000_000
THEMES = {"dark", "light"}
RATE_UNITS = {"s", "m"}


@dataclass
class Config:
    theme: str = "dark"
    output_dir: str = "output"
    target_digits: int = 10_000_000
    refresh_interval_s: float = 1.0
    autosave_interval_s: int = 300
    memory_limit_gb: float = 8.0
    view_keep_chars: int = 200_000
    rate_unit: str = "s"
    bbp_default_hex_position: int = 1_000_000
    bbp_default_count: int = 16
    recent_outputs: list[str] = field(default_factory=list)


def sanitize(config: Config) -> Config:
    if config.theme not in THEMES:
        config.theme = "dark"
    if config.rate_unit not in RATE_UNITS:
        config.rate_unit = "s"
    config.target_digits = min(max(config.target_digits, TARGET_DIGITS_MIN), TARGET_DIGITS_MAX)
    config.refresh_interval_s = max(config.refresh_interval_s, 0.1)
    config.autosave_interval_s = max(config.autosave_interval_s, 10)
    config.memory_limit_gb = max(config.memory_limit_gb, 0.5)
    config.view_keep_chars = max(config.view_keep_chars, 10_000)
    config.bbp_default_hex_position = max(config.bbp_default_hex_position, 0)
    config.bbp_default_count = min(max(config.bbp_default_count, 1), 64)
    config.recent_outputs = list(config.recent_outputs[:20])
    return config


def load_settings(path: Path) -> Config:
    if not path.exists():
        return sanitize(Config())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sanitize(Config())
    known = {key: value for key, value in raw.items() if key in Config.__dataclass_fields__}
    return sanitize(Config(**known))


def save_settings(path: Path, config: Config) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
```

- [ ] **Step 4: 写 `pi_tool/common/protocol.py`**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PauseCommand:
    pass


@dataclass(frozen=True)
class ResumeRunCommand:
    pass


@dataclass(frozen=True)
class SaveCommand:
    pass


@dataclass(frozen=True)
class StopCommand:
    pass


@dataclass(frozen=True)
class BbpCheckCommand:
    position: int
    count: int


@dataclass(frozen=True)
class UpdateSettingsCommand:
    refresh_interval_s: float
    autosave_interval_s: float
    memory_limit_bytes: int


@dataclass(frozen=True)
class ProgressEvent:
    terms_done: int
    stable_digits: int
    written_digits: int
    rate_digits_per_s: float
    eta_seconds: float | None
    mem_bytes: int
    chunk_text: str


@dataclass(frozen=True)
class PausedEvent:
    reason: str
    written_digits: int


@dataclass(frozen=True)
class SavedEvent:
    path: str
    written_digits: int


@dataclass(frozen=True)
class DoneEvent:
    total_digits: int
    sha256: str


@dataclass(frozen=True)
class BbpResultEvent:
    position: int
    count: int
    expected: str
    got: str
    ok: bool


@dataclass(frozen=True)
class ErrorEvent:
    message: str


@dataclass(frozen=True)
class LogEvent:
    level: str
    message: str
```

- [ ] **Step 5: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_config.py -q`
预期：`5 passed`。

- [ ] **Step 6: 提交**

```
git add pi_tool/common/config.py
git commit -m "feat. 实现设置数据类与 settings.json 原子读写（含钳制）"
git add pi_tool/common/protocol.py
git commit -m "feat. 定义 worker 命令/事件协议数据类"
git add tests/test_config.py
git commit -m "test. 添加配置钳制与协议可序列化测试"
```

---

### Task 10: worker 主循环与端到端一致性

**Covers:** [S5], [S6], [S11]

**Files:**
- Create: `pi_tool/engine/worker.py`, `tests/test_worker_e2e.py`

**Interfaces:**
- Consumes: 此前全部模块
- Produces:
  - `insert_linebreaks(text: str, stream_chars_before: int, width: int = 1000) -> str`
  - `run_calculator(events, commands, output_dir, target_digits, refresh_interval_s, autosave_interval_s, memory_limit_bytes, resume: bool, pause_after_chunks: int | None = None) -> None`（模块级函数，可直接作为 `multiprocessing.Process(target=...)`；GUI 与 CLI 共用）
  - `spawn_worker(events, commands, output_dir, target_digits, refresh_interval_s, autosave_interval_s, memory_limit_bytes, resume) -> multiprocessing.Process`
  - CLI：`.venv\Scripts\python.exe -m pi_tool.engine.worker --output-dir DIR --target-digits N [--resume] [--pause-after-chunks K]`
  - 语义要点（供 GUI/README 引用）：
    - `written_digits ≥ target_digits`（完成时写出的是全部"稳定位"，通常比目标多几十位，且对同一目标恒为同一值 → 确定性不受影响）
    - 暂停点任意、重启任意次，最终 `pi.txt` 字节与一次性计算完全一致
    - 队列只承载运行中命令；启动参数走进程参数

- [ ] **Step 1: 写失败测试 `tests/test_worker_e2e.py`**

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def _run_worker(args: list[str]) -> None:
    subprocess.run(
        [str(PYTHON), "-m", "pi_tool.engine.worker", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _read_session(directory: Path) -> dict:
    return json.loads((directory / "pi.session.json").read_text(encoding="utf-8"))


def test_pause_resume_matches_one_shot(tmp_path):
    target = 100_000
    one_shot = tmp_path / "one"
    _run_worker(["--output-dir", str(one_shot), "--target-digits", str(target)])

    multi = tmp_path / "multi"
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--pause-after-chunks", "1"])
    assert _read_session(multi)["status"] == "paused"
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--resume", "--pause-after-chunks", "1"])
    assert _read_session(multi)["status"] == "paused"
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--resume"])

    assert (one_shot / "pi.txt").read_bytes() == (multi / "pi.txt").read_bytes()
    assert _read_session(one_shot)["sha256_final"] == _read_session(multi)["sha256_final"]


def test_degraded_resume_without_checkpoint(tmp_path):
    target = 50_000
    multi = tmp_path / "multi"
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--pause-after-chunks", "1"])
    (multi / "pi.checkpoint.bin").unlink()
    _run_worker(["--output-dir", str(multi), "--target-digits", str(target), "--resume"])

    one_shot = tmp_path / "one"
    _run_worker(["--output-dir", str(one_shot), "--target-digits", str(target)])
    assert (one_shot / "pi.txt").read_bytes() == (multi / "pi.txt").read_bytes()


def test_line_format_and_prefix(tmp_path):
    target = 100_000
    directory = tmp_path / "one"
    _run_worker(["--output-dir", str(directory), "--target-digits", str(target)])
    text = (directory / "pi.txt").read_text(encoding="ascii")
    assert text.endswith("\n")
    lines = text.split("\n")
    assert lines[-1] == ""
    body = lines[:-1]
    assert len(body[0]) == 1000 and body[0].startswith("3.")
    for line in body[1:-1]:
        assert len(line) == 1000 and line.isdigit()
    assert body[-1].isdigit() and 1 <= len(body[-1]) <= 1000
    digits = "".join(body)
    assert digits.startswith("3.14159265358979323846264338327950288419716939937510")
    session = _read_session(directory)
    assert len(digits) - 2 == session["written_digits"] >= target


def test_session_fields(tmp_path):
    directory = tmp_path / "one"
    _run_worker(["--output-dir", str(directory), "--target-digits", str(20_000)])
    session = _read_session(directory)
    assert session["schema_version"] == 1
    assert session["status"] == "completed"
    assert session["algorithm"] == "chudnovsky-bs-v1"
    assert session["target_digits"] == 20_000
    assert sum(session["digit_counts"]) == session["written_digits"]
    assert len(session["sha256_final"]) == 64
    assert (directory / "pi.checkpoint.bin").exists()
    assert (directory / "pi.log").exists()
```

- [ ] **Step 2: 运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_worker_e2e.py -q`
预期：FAIL（worker 模块不存在）。

- [ ] **Step 3: 写 `pi_tool/engine/worker.py`**

```python
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import queue
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import psutil

from ..common.constants import (
    ALGORITHM_ID,
    DIGITS_PER_TERM,
    GUARD_DIGITS,
    LEAF_CUTOFF_INITIAL,
    PI_FIRST_100,
    STABLE_MARGIN,
    stable_digits_for_terms,
    terms_for_digits,
)
from ..common.protocol import (
    BbpCheckCommand,
    BbpResultEvent,
    DoneEvent,
    ErrorEvent,
    LogEvent,
    PauseCommand,
    PausedEvent,
    ProgressEvent,
    ResumeRunCommand,
    SaveCommand,
    SavedEvent,
    StopCommand,
    UpdateSettingsCommand,
)
from . import checkpoint as checkpoint_module
from .chudnovsky import SeriesState
from .decimal import NotEnoughTerms, pi_prefix_decimal
from .verify import bbp_crosscheck, sha256_file

LINE_WIDTH = 1000
CHUNK_TARGET_SECONDS = 1.0
INITIAL_CHUNK_TERMS = 4096
MIN_REFRESH_STEP = 100_000
FSYNC_THRESHOLD_BYTES = 16 * 1024 * 1024
PROGRESS_INTERVAL_SECONDS = 0.15
LOG_MAX_BYTES = 5 * 1024 * 1024


def insert_linebreaks(text: str, stream_chars_before: int, width: int = LINE_WIDTH) -> str:
    """在字符流每累计 width 个字符后插入换行（stream_chars_before 为已写入流长）。"""
    pieces: list[str] = []
    cursor = 0
    position = stream_chars_before
    while cursor < len(text):
        boundary = (position // width + 1) * width
        take = min(boundary - position, len(text) - cursor)
        pieces.append(text[cursor : cursor + take])
        cursor += take
        position += take
        if position % width == 0:
            pieces.append("\n")
    return "".join(pieces)


class DigitFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None
        self.written_digits = 0
        self.unsynced_bytes = 0

    def open(self, resume_written: int | None) -> int:
        if resume_written is None or not self.path.exists():
            self.handle = open(self.path, "wb")
            self.written_digits = 0
            return 0
        stream_length = 2 + resume_written
        expected_bytes = stream_length + stream_length // LINE_WIDTH
        self.handle = open(self.path, "r+b")
        size = os.fstat(self.handle.fileno()).st_size
        if size < expected_bytes:
            self.handle.truncate(0)
            self.handle.seek(0)
            self.written_digits = 0
            return 0
        self.handle.truncate(expected_bytes)
        self.handle.seek(expected_bytes)
        self.written_digits = resume_written
        return resume_written

    def append(self, digits: str) -> None:
        text = insert_linebreaks(digits, 2 + self.written_digits)
        self.handle.write(text.encode("ascii"))
        self.written_digits += len(digits)
        self.unsynced_bytes += len(text)
        if self.unsynced_bytes >= FSYNC_THRESHOLD_BYTES:
            self.flush_sync()

    def flush_sync(self) -> None:
        if self.handle is None:
            return
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.unsynced_bytes = 0

    def finalize(self) -> None:
        if self.handle is None:
            return
        if (2 + self.written_digits) % LINE_WIDTH != 0:
            self.handle.write(b"\n")
        self.flush_sync()
        self.handle.close()
        self.handle = None


def write_session(path: Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class Calculator:
    def __init__(
        self,
        events,
        output_dir: Path,
        target_digits: int,
        refresh_interval_s: float,
        autosave_interval_s: float,
        memory_limit_bytes: int,
    ) -> None:
        self.events = events
        self.output_dir = output_dir
        self.target_digits = target_digits
        self.refresh_interval_s = refresh_interval_s
        self.autosave_interval_s = autosave_interval_s
        self.memory_limit_bytes = memory_limit_bytes
        self.state = SeriesState()
        self.target_terms = terms_for_digits(target_digits)
        self.planned_stable = stable_digits_for_terms(self.target_terms)
        self.min_refresh_step = max(1_000, min(MIN_REFRESH_STEP, self.planned_stable // 4))
        self.digit_file = DigitFile(output_dir / "pi.txt")
        self.session_path = output_dir / "pi.session.json"
        self.checkpoint_path = output_dir / "pi.checkpoint.bin"
        self.started_at = time.perf_counter()
        self.elapsed_before = 0.0
        self.chunk_rates: deque[tuple[int, float]] = deque(maxlen=20)
        self.last_progress_at = 0.0
        self.last_refresh_at = 0.0
        self.last_refresh_stable = 0
        self.next_refresh_not_before = 0.0
        self.last_autosave_at = time.perf_counter()
        self.digit_counts = [0] * 10
        self.status = "running"
        self.process = psutil.Process()
        self.chunks_done = 0
        self.pending_chunk_text = ""
        self.sha256_final: str | None = None
        self.created_at = datetime.now().astimezone().isoformat(timespec="seconds")

    # ---------- 状态与统计 ----------

    def elapsed(self) -> float:
        return self.elapsed_before + (time.perf_counter() - self.started_at)

    def term_rate(self) -> float:
        total_terms = sum(terms for terms, _ in self.chunk_rates)
        total_time = sum(seconds for _, seconds in self.chunk_rates)
        return total_terms / total_time if total_time > 0 else 0.0

    def digit_rate(self) -> float:
        return self.term_rate() * DIGITS_PER_TERM

    def eta_seconds(self) -> float | None:
        remaining = self.target_terms - self.state.terms
        if remaining <= 0:
            return 0.0
        rate = self.term_rate()
        return remaining / rate if rate > 0 else None

    def next_chunk_terms(self) -> int:
        remaining = self.target_terms - self.state.terms
        rate = self.term_rate()
        if rate <= 0:
            return min(INITIAL_CHUNK_TERMS, remaining)
        return max(1, min(int(rate * CHUNK_TARGET_SECONDS), remaining))

    # ---------- 日志 ----------

    def emit_log(self, level: str, message: str) -> None:
        self.events.put(LogEvent(level=level, message=message))
        line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} [{level}] {message}\n"
        log_path = self.output_dir / "pi.log"
        try:
            if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
                for index in range(2, 0, -1):
                    source = log_path.with_name(f"pi.log.{index}")
                    if source.exists():
                        source.replace(log_path.with_name(f"pi.log.{index + 1}"))
                log_path.replace(log_path.with_name("pi.log.1"))
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass

    # ---------- 数字写出 ----------

    def count_digits(self, text: str) -> None:
        for digit in "0123456789":
            self.digit_counts[int(digit)] += text.count(digit)

    def append_stable_digits(self) -> None:
        stable = stable_digits_for_terms(self.state.terms)
        if stable <= self.digit_file.written_digits:
            return
        prefix = pi_prefix_decimal(self.state, stable)
        new_digits = prefix[self.digit_file.written_digits :]
        self.digit_file.append(new_digits)
        self.count_digits(new_digits)
        self.pending_chunk_text += new_digits
        self.last_refresh_stable = stable

    def maybe_refresh(self) -> None:
        stable = stable_digits_for_terms(self.state.terms)
        if stable <= self.digit_file.written_digits:
            return
        required_step = max(self.min_refresh_step, self.last_refresh_stable // 100)
        if stable - self.last_refresh_stable < required_step:
            return
        now = time.perf_counter()
        if now < self.next_refresh_not_before or now - self.last_refresh_at < self.refresh_interval_s:
            return
        started = time.perf_counter()
        self.append_stable_digits()
        cost = time.perf_counter() - started
        self.last_refresh_at = time.perf_counter()
        if cost > 0.25:
            self.next_refresh_not_before = time.perf_counter() + 4 * cost

    # ---------- 事件 ----------

    def maybe_emit_progress(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.last_progress_at < PROGRESS_INTERVAL_SECONDS:
            return
        self.last_progress_at = now
        chunk_text = self.pending_chunk_text
        self.pending_chunk_text = ""
        self.events.put(
            ProgressEvent(
                terms_done=self.state.terms,
                stable_digits=stable_digits_for_terms(self.state.terms),
                written_digits=self.digit_file.written_digits,
                rate_digits_per_s=self.digit_rate(),
                eta_seconds=self.eta_seconds(),
                mem_bytes=self.process.memory_info().rss,
                chunk_text=chunk_text,
            )
        )

    # ---------- 持久化 ----------

    def snapshot_config(self) -> dict:
        return {
            "algorithm": ALGORITHM_ID,
            "target_digits": self.target_digits,
            "digits_per_term": DIGITS_PER_TERM,
            "guard_digits": GUARD_DIGITS,
            "stable_margin": STABLE_MARGIN,
        }

    def persist_session(self, status: str | None = None) -> None:
        payload = {
            "schema_version": 1,
            "status": status or self.status,
            "algorithm": ALGORITHM_ID,
            "target_digits": self.target_digits,
            "written_digits": self.digit_file.written_digits,
            "stable_digits": stable_digits_for_terms(self.state.terms),
            "terms_done": self.state.terms,
            "elapsed_seconds": round(self.elapsed(), 2),
            "created_at": self.created_at,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "output_file": "pi.txt",
            "digit_counts": list(self.digit_counts),
            "sha256_final": self.sha256_final,
        }
        write_session(self.session_path, payload)

    def save_all(self, session_status: str | None = None) -> None:
        stable = stable_digits_for_terms(self.state.terms)
        checkpoint_module.save(self.checkpoint_path, self.state, stable, self.snapshot_config())
        self.digit_file.flush_sync()
        self.persist_session(session_status)

    # ---------- 恢复 ----------

    def resume_from_disk(self) -> bool:
        if not self.session_path.exists():
            self.digit_file.open(resume_written=None)
            return False
        session = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.digit_counts = list(session.get("digit_counts") or [0] * 10)
        self.elapsed_before = float(session.get("elapsed_seconds", 0.0))
        written = int(session.get("written_digits", 0))
        actual = self.digit_file.open(resume_written=written)
        if actual == 0 and written > 0:
            self.digit_counts = [0] * 10
            self.emit_log("warning", "pi.txt 与记录不一致，已从头重写数字")
        try:
            loaded = checkpoint_module.load(self.checkpoint_path, self.snapshot_config())
        except (OSError, checkpoint_module.CheckpointError) as error:
            terms_done = int(session.get("terms_done", 0))
            self.state = SeriesState()
            self.state.extend(terms_done)
            self.emit_log("warning", f"检查点不可用（{error}），已降级重演到第 {terms_done:,} 项")
            return True
        self.state = SeriesState()
        self.state.terms = loaded.terms
        self.state.triple = loaded.triple
        self.emit_log("info", f"已从检查点恢复：第 {loaded.terms:,} 项 / 已写 {self.digit_file.written_digits:,} 位")
        return True

    # ---------- 命令 ----------

    def apply_settings(self, command: UpdateSettingsCommand) -> None:
        self.refresh_interval_s = max(command.refresh_interval_s, 0.1)
        self.autosave_interval_s = max(command.autosave_interval_s, 10.0)
        self.memory_limit_bytes = max(command.memory_limit_bytes, 1)

    def run_bbp_check(self, command: BbpCheckCommand) -> None:
        self.emit_log("info", f"BBP 校验开始：十六进制第 {command.position:,} 位（{command.count} 位）")
        started = time.perf_counter()
        try:
            expected, got, ok = bbp_crosscheck(self.state, command.position, command.count)
        except NotEnoughTerms:
            self.events.put(ErrorEvent(message="尚未计算到该位置，请先继续计算"))
            return
        self.events.put(
            BbpResultEvent(position=command.position, count=command.count, expected=expected, got=got, ok=ok)
        )
        verdict = "一致" if ok else "不一致"
        self.emit_log("info", f"BBP 校验完成（{time.perf_counter() - started:.1f} 秒）：{verdict}")

    def pause_and_save(self) -> None:
        self.status = "paused"
        self.append_stable_digits()
        self.save_all(session_status="paused")
        self.maybe_emit_progress(force=True)
        self.emit_log("info", f"已暂停并保存：{self.digit_file.written_digits:,} 位")

    def wait_while_paused(self, commands) -> str:
        while True:
            command = commands.get(block=True)
            if isinstance(command, ResumeRunCommand):
                self.status = "running"
                self.emit_log("info", "继续计算")
                return "continue"
            if isinstance(command, StopCommand):
                self.status = "stopped"
                self.persist_session("stopped")
                self.emit_log("info", "已停止（进度已保存，可随时继续）")
                return "stop"
            if isinstance(command, SaveCommand):
                self.save_all()
                self.events.put(
                    SavedEvent(path=str(self.session_path), written_digits=self.digit_file.written_digits)
                )
            if isinstance(command, UpdateSettingsCommand):
                self.apply_settings(command)

    def dispatch(self, command, commands) -> str:
        if isinstance(command, PauseCommand):
            self.pause_and_save()
            self.events.put(PausedEvent(reason="user", written_digits=self.digit_file.written_digits))
            return self.wait_while_paused(commands)
        if isinstance(command, StopCommand):
            self.pause_and_save()
            self.status = "stopped"
            self.persist_session("stopped")
            return "stop"
        if isinstance(command, SaveCommand):
            self.append_stable_digits()
            self.save_all()
            self.events.put(SavedEvent(path=str(self.session_path), written_digits=self.digit_file.written_digits))
            return "continue"
        if isinstance(command, BbpCheckCommand):
            self.run_bbp_check(command)
            return "continue"
        if isinstance(command, UpdateSettingsCommand):
            self.apply_settings(command)
            return "continue"
        return "continue"

    def poll_commands(self, commands, blocking: bool) -> str:
        while True:
            try:
                command = commands.get(block=blocking, timeout=None if blocking else 0.0)
            except queue.Empty:
                return "continue"
            action = self.dispatch(command, commands)
            if action != "continue":
                return action
            blocking = False

    # ---------- 内存与收尾 ----------

    def check_memory(self, commands) -> str:
        if self.process.memory_info().rss <= self.memory_limit_bytes:
            return "continue"
        self.pause_and_save()
        self.events.put(PausedEvent(reason="memory", written_digits=self.digit_file.written_digits))
        self.emit_log("warning", "内存超过阈值，已自动暂停")
        return self.wait_while_paused(commands)

    def finish(self) -> None:
        self.append_stable_digits()
        self.digit_file.finalize()
        if self.target_digits >= 100 and pi_prefix_decimal(self.state, 100) != PI_FIRST_100:
            self.events.put(ErrorEvent(message="完成后自检失败：前 100 位与权威常数不符"))
        self.sha256_final = sha256_file(self.digit_file.path)
        self.status = "completed"
        self.persist_session("completed")
        self.maybe_emit_progress(force=True)
        self.events.put(DoneEvent(total_digits=self.digit_file.written_digits, sha256=self.sha256_final))
        self.emit_log("info", f"完成：{self.digit_file.written_digits:,} 位，SHA-256 {self.sha256_final}")

    def loop(self, commands, pause_after_chunks: int | None) -> None:
        self.maybe_emit_progress(force=True)
        while self.state.terms < self.target_terms:
            if self.poll_commands(commands, blocking=False) == "stop":
                return
            chunk_terms = self.next_chunk_terms()
            started = time.perf_counter()
            self.state.extend(chunk_terms, LEAF_CUTOFF_INITIAL)
            self.chunk_rates.append((chunk_terms, time.perf_counter() - started))
            self.chunks_done += 1
            self.maybe_refresh()
            self.maybe_emit_progress()
            if self.autosave_interval_s > 0 and time.perf_counter() - self.last_autosave_at >= self.autosave_interval_s:
                self.last_autosave_at = time.perf_counter()
                self.append_stable_digits()
                self.save_all(session_status="running")
                self.events.put(SavedEvent(path=str(self.session_path), written_digits=self.digit_file.written_digits))
            if pause_after_chunks is not None and self.chunks_done >= pause_after_chunks:
                self.pause_and_save()
                self.events.put(PausedEvent(reason="user", written_digits=self.digit_file.written_digits))
                return
            if self.check_memory(commands) == "stop":
                return
        self.finish()


def run_calculator(
    events,
    commands,
    output_dir,
    target_digits: int,
    refresh_interval_s: float,
    autosave_interval_s: float,
    memory_limit_bytes: int,
    resume: bool,
    pause_after_chunks: int | None = None,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    calculator = Calculator(events, output_dir, target_digits, refresh_interval_s, autosave_interval_s, memory_limit_bytes)
    try:
        resumed = resume and calculator.resume_from_disk()
        if not resumed:
            calculator.digit_file.open(resume_written=None)
            calculator.state = SeriesState()
        calculator.emit_log("info", f"{'继续' if resumed else '开始'}计算：目标 {target_digits:,} 位，算法 {ALGORITHM_ID}")
        calculator.loop(commands, pause_after_chunks)
    except Exception as error:  # noqa: BLE001 — 进程边界必须把异常上报给 GUI
        events.put(ErrorEvent(message=f"计算中断：{error}"))
        calculator.emit_log("error", f"计算中断：{error}")


def spawn_worker(
    events,
    commands,
    output_dir,
    target_digits: int,
    refresh_interval_s: float,
    autosave_interval_s: float,
    memory_limit_bytes: int,
    resume: bool,
) -> multiprocessing.Process:
    process = multiprocessing.Process(
        target=run_calculator,
        args=(
            events,
            commands,
            str(output_dir),
            target_digits,
            refresh_interval_s,
            autosave_interval_s,
            memory_limit_bytes,
            resume,
        ),
        daemon=True,
        name="pi-calculator-worker",
    )
    process.start()
    return process


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pi_tool worker（无 GUI 模式，供测试与调试）")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-digits", type=int, default=10_000_000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--pause-after-chunks", type=int, default=None)
    parser.add_argument("--refresh-interval", type=float, default=1.0)
    parser.add_argument("--autosave-interval", type=float, default=300.0)
    parser.add_argument("--memory-limit-gb", type=float, default=8.0)
    args = parser.parse_args(argv)
    events = multiprocessing.Queue()
    commands = multiprocessing.Queue()
    run_calculator(
        events,
        commands,
        args.output_dir,
        args.target_digits,
        args.refresh_interval,
        args.autosave_interval,
        int(args.memory_limit_gb * (1024**3)),
        args.resume,
        args.pause_after_chunks,
    )
    session_path = Path(args.output_dir) / "pi.session.json"
    if session_path.exists():
        print(session_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
```

- [ ] **Step 4: 运行测试确认通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_worker_e2e.py -q`
预期：`4 passed`（含"暂停两次 + 无检查点降级 + 一次性"三条路径字节一致）。
若 `test_pause_resume_matches_one_shot` 失败：先核对 `insert_linebreaks` 的边界语义（换行落在"流位置为 1000 的倍数"处），再核对 `DigitFile.open` 的 `expected_bytes = stream_length + stream_length // LINE_WIDTH`。

- [ ] **Step 5: 全量回归**

运行：`.venv\Scripts\python.exe -m pytest tests -q`
预期：全部通过（截至本任务共 40+ 用例）。

- [ ] **Step 6: 提交**

```
git add pi_tool/engine/worker.py
git commit -m "feat. 实现 worker 主循环（分块计算/暂停续算/检查点/内存监控/BBP 校验/CLI）"
git add tests/test_worker_e2e.py
git commit -m "test. 添加端到端一致性测试（暂停续算/降级恢复/行格式/会话字段）"
```

---

### Task 11: 主题、控件与对话框

**Covers:** [S7]

**Files:**
- Create: `pi_tool/app/theme.py`, `pi_tool/app/widgets.py`

**Interfaces:**
- Consumes: `Config`（Task 9）
- Produces:
  - `theme.apply_theme(app: QApplication, name: str) -> None`（`"light"` 之外一律深色）
  - `theme.DIGIT_FONT_FAMILIES: list[str]`、`theme.DIGIT_FONT_POINT_SIZE: int`
  - `widgets.DigitView(QPlainTextEdit)`：`__init__(keep_chars: int = 200_000)`、`append_digits(chunk: str) -> None`（只保留尾窗、自动滚尾；超大块安全）
  - `widgets.RatePanel(QWidget)`：含 `rate_label`、`unit_combo`（`itemData` 为 `"s"`/`"m"`）、`memory_bar`（`state` property ∈ ok/warn/danger）、`memory_label`；方法 `set_rate(digits_per_second: float, unit: str)`、`set_memory(used_bytes: int, limit_bytes: int)`
  - `widgets.FrequencyChart(QWidget)`：`set_counts(counts: list[int]) -> None`
  - `widgets.NewSessionDialog(QDialog)`：`values() -> tuple[int, str]`（目标位数、输出目录）

- [ ] **Step 1: 写 `pi_tool/app/theme.py`**

```python
from __future__ import annotations

from PySide6.QtWidgets import QApplication

DIGIT_FONT_FAMILIES = ["JetBrains Mono", "Consolas", "Menlo", "Monospace"]
DIGIT_FONT_POINT_SIZE = 13

DARK_QSS = """
QWidget { background-color: #1e1f22; color: #e6e6e6; font-size: 13px; }
QMainWindow, QDialog { background-color: #1e1f22; }
QPushButton { background-color: #3a3d42; border: none; border-radius: 8px; padding: 8px 16px; }
QPushButton:hover:!disabled { background-color: #4a4e55; }
QPushButton:disabled { color: #77787b; background-color: #2b2d31; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTableWidget {
    background-color: #2b2d31; border: 1px solid #3a3d42; border-radius: 6px; padding: 4px;
}
QProgressBar { background-color: #2b2d31; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background-color: #4f8cff; border-radius: 6px; }
QProgressBar[state="warn"]::chunk { background-color: #e0a63c; }
QProgressBar[state="danger"]::chunk { background-color: #d9534f; }
QTabWidget::pane { border: 1px solid #3a3d42; border-radius: 8px; }
QTabBar::tab { background: #2b2d31; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #4f8cff; color: #ffffff; }
QHeaderView::section { background-color: #2b2d31; border: none; padding: 4px; }
QStatusBar { background-color: #2b2d31; }
#rateLabel { font-size: 22px; font-weight: 600; color: #7fb2ff; }
"""

LIGHT_QSS = """
QWidget { background-color: #f5f6f8; color: #1f2328; font-size: 13px; }
QMainWindow, QDialog { background-color: #f5f6f8; }
QPushButton { background-color: #e3e6ea; border: none; border-radius: 8px; padding: 8px 16px; }
QPushButton:hover:!disabled { background-color: #d5dae0; }
QPushButton:disabled { color: #9aa0a6; background-color: #eceef1; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTableWidget {
    background-color: #ffffff; border: 1px solid #d0d4da; border-radius: 6px; padding: 4px;
}
QProgressBar { background-color: #e3e6ea; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background-color: #3574e0; border-radius: 6px; }
QProgressBar[state="warn"]::chunk { background-color: #d08700; }
QProgressBar[state="danger"]::chunk { background-color: #c0392b; }
QTabWidget::pane { border: 1px solid #d0d4da; border-radius: 8px; }
QTabBar::tab { background: #e3e6ea; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #3574e0; color: #ffffff; }
QHeaderView::section { background-color: #eceef1; border: none; padding: 4px; }
QStatusBar { background-color: #eceef1; }
#rateLabel { font-size: 22px; font-weight: 600; color: #2456b8; }
"""


def apply_theme(app: QApplication, name: str) -> None:
    app.setStyleSheet(LIGHT_QSS if name == "light" else DARK_QSS)
```

- [ ] **Step 2: 写 `pi_tool/app/widgets.py`**

```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..common.config import TARGET_DIGITS_MAX, TARGET_DIGITS_MIN, Config
from .theme import DIGIT_FONT_FAMILIES, DIGIT_FONT_POINT_SIZE

VIEW_MAX_INSERT = 2_000_000


class DigitView(QPlainTextEdit):
    def __init__(self, keep_chars: int = 200_000) -> None:
        super().__init__()
        self.keep_chars = keep_chars
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont()
        font.setFamilies(DIGIT_FONT_FAMILIES)
        font.setPointSize(DIGIT_FONT_POINT_SIZE)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setPlaceholderText("等待开始计算…")
        self.setPlainText("3.")

    def append_digits(self, chunk: str) -> None:
        if not chunk:
            return
        if len(chunk) >= self.keep_chars:
            self.setPlainText(chunk[-self.keep_chars :])
        elif len(chunk) > VIEW_MAX_INSERT:
            merged = (self.toPlainText() + chunk)[-self.keep_chars :]
            self.setPlainText(merged)
        else:
            self.moveCursor(QTextCursor.MoveOperation.End)
            self.insertPlainText(chunk)
            overflow = self.document().characterCount() - 1 - self.keep_chars
            if overflow > 0:
                cursor = self.textCursor()
                cursor.setPosition(0)
                cursor.setPosition(overflow, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class RatePanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.rate_label = QLabel("0 位/秒")
        self.rate_label.setObjectName("rateLabel")
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("位/秒", "s")
        self.unit_combo.addItem("位/分", "m")
        self.memory_bar = QProgressBar()
        self.memory_bar.setRange(0, 100)
        self.memory_bar.setTextVisible(False)
        self.memory_bar.setFixedWidth(220)
        self.memory_label = QLabel("内存 0.00 GB / 0.0 GB")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.rate_label)
        layout.addWidget(self.unit_combo)
        layout.addStretch(1)
        layout.addWidget(self.memory_label)
        layout.addWidget(self.memory_bar)

    def set_rate(self, digits_per_second: float, unit: str) -> None:
        value = digits_per_second * 60 if unit == "m" else digits_per_second
        suffix = "位/分" if unit == "m" else "位/秒"
        self.rate_label.setText(f"{value:,.0f} {suffix}")

    def set_memory(self, used_bytes: int, limit_bytes: int) -> None:
        used_gb = used_bytes / (1024**3)
        limit_gb = limit_bytes / (1024**3)
        percent = int(min(100, used_gb / limit_gb * 100)) if limit_gb > 0 else 0
        self.memory_label.setText(f"内存 {used_gb:.2f} GB / {limit_gb:.1f} GB")
        self.memory_bar.setValue(percent)
        state = "danger" if percent >= 95 else "warn" if percent >= 80 else "ok"
        self.memory_bar.setProperty("state", state)
        self.memory_bar.style().unpolish(self.memory_bar)
        self.memory_bar.style().polish(self.memory_bar)


class FrequencyChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.counts = [0] * 10
        self.setMinimumHeight(170)

    def set_counts(self, counts: list[int]) -> None:
        self.counts = list(counts)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        maximum = max(self.counts) if any(self.counts) else 1
        slot = width / 10
        painter.setPen(self.palette().color(self.foregroundRole()))
        for index, count in enumerate(self.counts):
            bar_height = int((height - 34) * count / maximum)
            painter.fillRect(
                int(index * slot + slot * 0.15),
                height - 22 - bar_height,
                int(slot * 0.7),
                bar_height,
                QColor("#4f8cff"),
            )
            painter.drawText(
                int(index * slot),
                height - 18,
                int(slot),
                18,
                Qt.AlignmentFlag.AlignCenter,
                f"{index}\n{count:,}" if count else str(index),
            )


class NewSessionDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新计算")
        self.setMinimumWidth(520)
        self.target_spin = QSpinBox()
        self.target_spin.setRange(TARGET_DIGITS_MIN, TARGET_DIGITS_MAX)
        self.target_spin.setValue(config.target_digits)
        self.target_spin.setGroupSeparatorShown(True)
        self.output_edit = QLineEdit(config.output_dir)
        browse_button = QPushButton("浏览…")
        browse_button.clicked.connect(self._browse)
        self.estimate_label = QLabel()
        self.estimate_label.setWordWrap(True)
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("目标位数"))
        target_row.addWidget(self.target_spin, 1)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录"))
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(target_row)
        layout.addLayout(output_row)
        layout.addWidget(self.estimate_label)
        layout.addWidget(buttons)
        self.target_spin.valueChanged.connect(self._update_estimate)
        self._update_estimate()

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text() or ".")
        if chosen:
            self.output_edit.setText(chosen)

    def _update_estimate(self) -> None:
        digits = self.target_spin.value()
        text_mb = digits / (1024 * 1024)
        checkpoint_mb = digits * 1.25 / (1024 * 1024)
        memory_gb = digits * 2.5 / (1024**3)
        self.estimate_label.setText(
            f"估算：pi.txt ≈ {text_mb:,.1f} MB ｜ 检查点 ≈ {checkpoint_mb:,.1f} MB ｜ 内存峰值 ≈ {memory_gb:,.2f} GB"
        )

    def values(self) -> tuple[int, str]:
        return self.target_spin.value(), (self.output_edit.text().strip() or "output")


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.refresh_spin = QDoubleSpinBox()
        self.refresh_spin.setRange(0.1, 60.0)
        self.refresh_spin.setDecimals(1)
        self.refresh_spin.setSuffix(" 秒")
        self.refresh_spin.setValue(config.refresh_interval_s)
        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(10, 3600)
        self.autosave_spin.setSuffix(" 秒")
        self.autosave_spin.setValue(config.autosave_interval_s)
        self.memory_spin = QDoubleSpinBox()
        self.memory_spin.setRange(0.5, 128.0)
        self.memory_spin.setDecimals(1)
        self.memory_spin.setSuffix(" GB")
        self.memory_spin.setValue(config.memory_limit_gb)
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(10_000, 5_000_000)
        self.keep_spin.setSingleStep(10_000)
        self.keep_spin.setValue(config.view_keep_chars)
        form = QVBoxLayout(self)
        for label, widget in (
            ("刷新间隔", self.refresh_spin),
            ("自动保存间隔", self.autosave_spin),
            ("内存阈值", self.memory_spin),
            ("显示保留字符数", self.keep_spin),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget, 1)
            form.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

    def apply_to(self, config: Config) -> Config:
        config.refresh_interval_s = self.refresh_spin.value()
        config.autosave_interval_s = self.autosave_spin.value()
        config.memory_limit_gb = self.memory_spin.value()
        config.view_keep_chars = self.keep_spin.value()
        return config
```
```
git add pi_tool/app/theme.py
git commit -m "feat. 添加深/浅两套 QSS 主题"
git add pi_tool/app/widgets.py
git commit -m "feat. 添加数字滚动区/速率面板/频率图/新计算与设置对话框"
```

- [ ] **Step 3: 离屏冒烟验证（无窗口环境可跑）**

运行：
```
.venv\Scripts\python.exe -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; app=QApplication([]); from pi_tool.app.theme import apply_theme; from pi_tool.app.widgets import DigitView, RatePanel, FrequencyChart, NewSessionDialog, SettingsDialog; from pi_tool.common.config import Config; apply_theme(app, 'dark'); apply_theme(app, 'light'); r=RatePanel(); r.set_rate(152340.0,'m'); r.set_memory(400*1024*1024, 8*1024**3); d=DigitView(1000); d.append_digits('0123456789'*500); c=FrequencyChart(); c.set_counts([1,2,3,4,5,6,7,8,9,10]); NewSessionDialog(Config()); SettingsDialog(Config()); print('widgets ok')"
```
预期输出：`widgets ok`。

---

### Task 12: 主窗口与辅助页（历史/搜索/导出/统计/BBP/日志）

**Covers:** [S1], [S6], [S7], [S8]

**Files:**
- Create: `pi_tool/app/history.py`, `pi_tool/app/search.py`, `pi_tool/app/export.py`, `pi_tool/app/main_window.py`

**Interfaces:**
- Consumes: Task 1–11 全部模块（尤其 `worker.spawn_worker`、`protocol`、`config`、`widgets`、`theme`）
- Produces:
  - `history.SessionInfo(directory: str, target_digits: int, written_digits: int, status: str, updated_at: str, file_size: int, sha256_prefix: str)`；`history.scan_sessions(directories: list[str]) -> list[SessionInfo]`；`history.remember_output(config: Config, directory: str) -> Config`
  - `search.SearchWorker(QThread)`：`__init__(path: Path, needle: str, limit: int = 100)`；信号 `finished_results = Signal(list)`（元素为 `(小数位序号1起, 匹配长度)`）、`failed = Signal(str)`
  - `export.gzip_export(source: Path, target: Path, on_progress=None) -> None`
  - `main_window.MainWindow(config: Config, settings_path: Path)`；`main_window.run_app(argv: list[str]) -> int`
  - 行为契约（[S7] 状态机）：空闲=仅"新计算/继续会话"可用；运行中="暂停/保存/停止"可用；暂停="保存/停止"可用；完成后="新计算/继续会话"可用

- [ ] **Step 1: 写 `pi_tool/app/history.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..common.config import Config


@dataclass(frozen=True)
class SessionInfo:
    directory: str
    target_digits: int
    written_digits: int
    status: str
    updated_at: str
    file_size: int
    sha256_prefix: str


def scan_sessions(directories: list[str]) -> list[SessionInfo]:
    found: list[SessionInfo] = []
    for directory in directories:
        base = Path(directory)
        session_path = base / "pi.session.json"
        text_file = base / "pi.txt"
        if not session_path.exists():
            continue
        try:
            raw = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sha = raw.get("sha256_final") or ""
        found.append(
            SessionInfo(
                directory=str(base),
                target_digits=int(raw.get("target_digits", 0)),
                written_digits=int(raw.get("written_digits", 0)),
                status=str(raw.get("status", "unknown")),
                updated_at=str(raw.get("updated_at", "")),
                file_size=text_file.stat().st_size if text_file.exists() else 0,
                sha256_prefix=sha[:16],
            )
        )
    found.sort(key=lambda item: item.updated_at, reverse=True)
    return found


def remember_output(config: Config, directory: str) -> Config:
    target = str(Path(directory))
    config.recent_outputs = [target] + [item for item in config.recent_outputs if item != target]
    config.recent_outputs = config.recent_outputs[:20]
    return config
```

- [ ] **Step 2: 写 `pi_tool/app/search.py`**

```python
from __future__ import annotations

import mmap
from pathlib import Path

from PySide6.QtCore import QThread, Signal

CHUNK_BYTES = 1 << 26


class SearchWorker(QThread):
    finished_results = Signal(list)
    failed = Signal(str)

    def __init__(self, path: Path, needle: str, limit: int = 100) -> None:
        super().__init__()
        self.path = path
        self.needle = needle
        self.limit = limit
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        needle = self.needle.encode("ascii")
        results: list[tuple[int, int]] = []
        carry = b""
        digits_seen = 0
        try:
            with open(self.path, "rb") as handle:
                with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as view:
                    position = 0
                    first = True
                    while position < len(view) and len(results) < self.limit and not self._cancelled:
                        block = view[position : position + CHUNK_BYTES]
                        position += CHUNK_BYTES
                        if first:
                            block = block[2:]
                            first = False
                        collapsed = block.replace(b"\n", b"")
                        data = carry + collapsed
                        start_index = digits_seen - len(carry)
                        at = data.find(needle)
                        while at != -1 and len(results) < self.limit:
                            results.append((start_index + at + 1, len(needle)))
                            at = data.find(needle, at + 1)
                        keep = len(needle) - 1
                        carry = data[-keep:] if keep else b""
                        digits_seen += len(collapsed)
            self.finished_results.emit(results)
        except OSError as error:
            self.failed.emit(str(error))
```

- [ ] **Step 3: 写 `pi_tool/app/export.py`**

```python
from __future__ import annotations

import gzip
from pathlib import Path


def gzip_export(source: Path, target: Path, on_progress=None) -> None:
    total = source.stat().st_size
    written = 0
    with open(source, "rb") as reader, gzip.open(target, "wb", compresslevel=6) as writer:
        while block := reader.read(1 << 20):
            writer.write(block)
            written += len(block)
            if on_progress is not None:
                on_progress(written, total)
```

- [ ] **Step 4: 写 `pi_tool/app/main_window.py`**

```python
from __future__ import annotations

import multiprocessing
import queue
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..common import protocol
from ..common.config import Config, load_settings, save_settings, sanitize
from ..engine.worker import spawn_worker
from .export import gzip_export
from .history import remember_output, scan_sessions
from .search import SearchWorker
from .theme import apply_theme
from .widgets import DigitView, FrequencyChart, NewSessionDialog, RatePanel, SettingsDialog

CLIPBOARD_LIMIT = 1_000_000
COPY_PREFIX_DEFAULT = 100_000
HEARTBEAT_TIMEOUT_S = 5.0


class MainWindow(QMainWindow):
    def __init__(self, config: Config, settings_path: Path) -> None:
        super().__init__()
        self.config = config
        self.settings_path = settings_path
        self.commands: multiprocessing.Queue | None = None
        self.events: multiprocessing.Queue | None = None
        self.worker: multiprocessing.Process | None = None
        self.search_worker: SearchWorker | None = None
        self.state = "idle"
        self.output_dir = Path(config.output_dir)
        self.memory_limit_bytes = int(config.memory_limit_gb * (1024**3))
        self._last_event_at = 0.0
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll_events)
        self._timer.start()
        self._update_buttons()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        self.setWindowTitle("π Calculator")
        self.resize(1120, 780)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        header = QHBoxLayout()
        self.theme_button = QPushButton("切换主题")
        self.theme_button.clicked.connect(self._toggle_theme)
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self._open_settings)
        header.addStretch(1)
        header.addWidget(self.theme_button)
        header.addWidget(settings_button)
        root.addLayout(header)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.digits_label = QLabel("位数 0")
        self.eta_label = QLabel("ETA —（估算）")
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 3)
        progress_row.addWidget(self.digits_label, 2)
        progress_row.addWidget(self.eta_label, 2)
        root.addLayout(progress_row)

        self.rate_panel = RatePanel()
        self.rate_panel.unit_combo.setCurrentIndex(0 if self.config.rate_unit == "s" else 1)
        self.rate_panel.unit_combo.currentIndexChanged.connect(self._change_rate_unit)
        root.addWidget(self.rate_panel)

        self.digit_view = DigitView(self.config.view_keep_chars)
        root.addWidget(self.digit_view, 2)

        controls = QHBoxLayout()
        self.new_button = QPushButton("新计算…")
        self.continue_button = QPushButton("继续会话")
        self.pause_button = QPushButton("暂停")
        self.save_button = QPushButton("立即保存")
        self.stop_button = QPushButton("停止")
        self.copy_button = QPushButton("复制前 10 万位")
        self.export_button = QPushButton("导出 gzip…")
        self.new_button.clicked.connect(self._new_session)
        self.continue_button.clicked.connect(self._resume_session)
        self.pause_button.clicked.connect(self._pause)
        self.save_button.clicked.connect(self._save_now)
        self.stop_button.clicked.connect(self._stop)
        self.copy_button.clicked.connect(self._copy_prefix)
        self.export_button.clicked.connect(self._export)
        for widget in (
            self.new_button,
            self.continue_button,
            self.pause_button,
            self.save_button,
            self.stop_button,
            self.copy_button,
            self.export_button,
        ):
            controls.addWidget(widget)
        controls.addStretch(1)
        root.addLayout(controls)

        self.tabs = QTabWidget()
        self.stats_chart = FrequencyChart()
        stats_page = QWidget()
        stats_layout = QVBoxLayout(stats_page)
        stats_layout.addWidget(self.stats_chart)
        self.stats_label = QLabel("统计随保存更新（完成时包含全部位数）")
        stats_layout.addWidget(self.stats_label)

        search_page = QWidget()
        search_layout = QVBoxLayout(search_page)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入要查找的数字串（空格会被忽略）")
        self.search_button = QPushButton("查找")
        self.search_button.clicked.connect(self._run_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        self.search_results = QPlainTextEdit()
        self.search_results.setReadOnly(True)
        search_layout.addLayout(search_row)
        search_layout.addWidget(self.search_results, 1)

        bbp_page = QWidget()
        bbp_layout = QVBoxLayout(bbp_page)
        bbp_row = QHBoxLayout()
        bbp_row.addWidget(QLabel("十六进制位位置"))
        self.bbp_position = QSpinBox()
        self.bbp_position.setRange(0, 2_000_000_000)
        self.bbp_position.setValue(self.config.bbp_default_hex_position)
        self.bbp_position.setGroupSeparatorShown(True)
        self.bbp_button = QPushButton("运行 BBP 校验")
        self.bbp_button.clicked.connect(self._run_bbp)
        bbp_row.addWidget(self.bbp_position)
        bbp_row.addWidget(self.bbp_button)
        bbp_row.addStretch(1)
        self.bbp_result = QPlainTextEdit()
        self.bbp_result.setReadOnly(True)
        bbp_layout.addLayout(bbp_row)
        bbp_layout.addWidget(self.bbp_result, 1)

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        self.rescan_button = QPushButton("重新扫描")
        self.rescan_button.clicked.connect(self._refresh_history)
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["目录", "目标", "已完成", "状态", "更新", "SHA-256"])
        self.history_table.cellDoubleClicked.connect(self._resume_from_history)
        history_layout.addWidget(self.rescan_button)
        history_layout.addWidget(self.history_table, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self.tabs.addTab(stats_page, "统计")
        self.tabs.addTab(search_page, "搜索")
        self.tabs.addTab(bbp_page, "BBP 校验")
        self.tabs.addTab(history_page, "历史")
        self.tabs.addTab(self.log_view, "日志")
        root.addWidget(self.tabs, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"输出目录：{self.output_dir}    SHA-256：完成后显示")
        self._refresh_history()

    # ---------- 状态机 ----------

    def _update_buttons(self) -> None:
        running = self.state == "running"
        paused = self.state == "paused"
        idle_like = self.state in {"idle", "completed", "stopped"}
        self.new_button.setEnabled(idle_like)
        self.continue_button.setEnabled(idle_like)
        self.pause_button.setEnabled(running)
        self.save_button.setEnabled(running or paused)
        self.stop_button.setEnabled(running or paused)
        self.bbp_button.setEnabled(running or paused)
        self.progress.setRange(0, 1000 if running or paused else 0)

    # ---------- worker 生命周期 ----------

    def _start_worker(self, output_dir: Path, target_digits: int, resume: bool) -> None:
        self.events = multiprocessing.Queue()
        self.commands = multiprocessing.Queue()
        self.memory_limit_bytes = int(self.config.memory_limit_gb * (1024**3))
        self.worker = spawn_worker(
            self.events,
            self.commands,
            output_dir,
            target_digits,
            self.config.refresh_interval_s,
            self.config.autosave_interval_s,
            self.memory_limit_bytes,
            resume,
        )
        self.output_dir = output_dir
        self.state = "running"
        if not resume:
            self.digit_view.setPlainText("3.")
            self.stats_chart.set_counts([0] * 10)
        self._update_buttons()
        self.statusBar().showMessage(f"输出目录：{output_dir}")

    def _new_session(self) -> None:
        dialog = NewSessionDialog(self.config, self)
        if dialog.exec() != NewSessionDialog.DialogCode.Accepted:
            return
        target_digits, output_dir = dialog.values()
        self.config.target_digits = target_digits
        self.config.output_dir = output_dir
        sanitize(self.config)
        remember_output(self.config, output_dir)
        save_settings(self.settings_path, self.config)
        self._start_worker(Path(output_dir), target_digits, resume=False)

    def _resume_session(self) -> None:
        sessions = scan_sessions(self.config.recent_outputs or [self.config.output_dir])
        resumable = [item for item in sessions if item.status != "completed"] or sessions
        if not resumable:
            QMessageBox.information(self, "继续会话", "没有可恢复的会话，请先开始一次新计算。")
            return
        latest = resumable[0]
        self._start_worker(Path(latest.directory), latest.target_digits, resume=True)

    def _resume_from_history(self, row: int, column: int) -> None:
        directory = self.history_table.item(row, 0).text()
        target = int(self.history_table.item(row, 1).text().replace(",", "") or self.config.target_digits)
        self._start_worker(Path(directory), target, resume=True)

    def _pause(self) -> None:
        self._send(protocol.PauseCommand())

    def _save_now(self) -> None:
        self._send(protocol.SaveCommand())

    def _stop(self) -> None:
        self._send(protocol.StopCommand())

    def _send(self, command) -> None:
        if self.commands is not None:
            self.commands.put(command)

    # ---------- 事件轮询 ----------

    def _poll_events(self) -> None:
        if self.events is None:
            return
        drained = 0
        while drained < 200:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            drained += 1
            self._handle_event(event)
        if self.worker is not None and self.state in {"running", "paused"} and not self.worker.is_alive():
            self._append_log("error", "计算进程已退出")
            self.worker = None
            self.state = "stopped"
            self._update_buttons()
            QMessageBox.warning(self, "计算中断", "计算进程意外结束。进度已保存在检查点中，可点击「继续会话」恢复。")

    def _handle_event(self, event) -> None:
        if isinstance(event, protocol.ProgressEvent):
            self._on_progress(event)
        elif isinstance(event, protocol.PausedEvent):
            self.state = "paused"
            self.rate_panel.set_rate(0.0, self._current_unit())
            note = "内存超限自动暂停" if event.reason == "memory" else "已暂停"
            self.statusBar().showMessage(f"{note}：已写 {event.written_digits:,} 位")
            self._update_buttons()
        elif isinstance(event, protocol.SavedEvent):
            self.statusBar().showMessage(f"已保存 {event.written_digits:,} 位 → {event.path}")
            self._refresh_history()
        elif isinstance(event, protocol.DoneEvent):
            self.state = "completed"
            self.worker = None
            self.statusBar().showMessage(f"完成 {event.total_digits:,} 位    SHA-256：{event.sha256}")
            self._update_buttons()
            self._refresh_history()
        elif isinstance(event, protocol.BbpResultEvent):
            verdict = "一致 ✔" if event.ok else "不一致 ✘"
            self.bbp_result.setPlainText(
                f"位置：十六进制第 {event.position:,} 位（{event.count} 位）\n"
                f"BBP 公式： {event.expected}\n"
                f"本引擎：   {event.got}\n"
                f"结论：{verdict}"
            )
        elif isinstance(event, protocol.ErrorEvent):
            self._append_log("error", event.message)
            QMessageBox.warning(self, "提示", event.message)
        elif isinstance(event, protocol.LogEvent):
            self._append_log(event.level, event.message)

    def _on_progress(self, event: protocol.ProgressEvent) -> None:
        if event.chunk_text:
            self.digit_view.append_digits(event.chunk_text)
        target = self.config.target_digits
        done = event.written_digits
        self.progress.setValue(int(min(1000, done / max(target, 1) * 1000)))
        self.digits_label.setText(f"位数 {done:,} / {target:,}")
        if event.eta_seconds is None:
            self.eta_label.setText("ETA —（估算）")
        else:
            minutes, seconds = divmod(int(event.eta_seconds), 60)
            hours, minutes = divmod(minutes, 60)
            self.eta_label.setText(f"ETA ~{hours}小时{minutes}分{seconds}秒（估算）")
        self.rate_panel.set_rate(event.rate_digits_per_s, self._current_unit())
        self.rate_panel.set_memory(event.mem_bytes, self.memory_limit_bytes)
        self.stats_label.setText(f"统计随保存更新（当前已写 {done:,} 位）")

    def _current_unit(self) -> str:
        return self.rate_panel.unit_combo.currentData() or "s"

    def _change_rate_unit(self) -> None:
        self.config.rate_unit = self._current_unit()
        save_settings(self.settings_path, self.config)

    def _append_log(self, level: str, message: str) -> None:
        self.log_view.appendPlainText(f"[{level}] {message}")

    # ---------- 设置 / 主题 / 历史 ----------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        dialog.apply_to(self.config)
        sanitize(self.config)
        save_settings(self.settings_path, self.config)
        self.memory_limit_bytes = int(self.config.memory_limit_gb * (1024**3))
        self.digit_view.keep_chars = self.config.view_keep_chars
        self._send(
            protocol.UpdateSettingsCommand(
                refresh_interval_s=self.config.refresh_interval_s,
                autosave_interval_s=float(self.config.autosave_interval_s),
                memory_limit_bytes=self.memory_limit_bytes,
            )
        )

    def _toggle_theme(self) -> None:
        self.config.theme = "light" if self.config.theme == "dark" else "dark"
        apply_theme(QApplication.instance(), self.config.theme)
        save_settings(self.settings_path, self.config)

    def _refresh_history(self) -> None:
        sessions = scan_sessions(self.config.recent_outputs or [self.config.output_dir])
        self.history_table.setRowCount(len(sessions))
        for row, item in enumerate(sessions):
            values = [
                item.directory,
                f"{item.target_digits:,}",
                f"{item.written_digits:,}",
                item.status,
                item.updated_at,
                item.sha256_prefix,
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(value))

    # ---------- 搜索 / BBP / 导出 / 复制 ----------

    def _run_search(self) -> None:
        needle = "".join(character for character in self.search_input.text() if character.isdigit())
        if not needle:
            return
        text_file = self.output_dir / "pi.txt"
        if not text_file.exists():
            self.search_results.setPlainText("尚无 pi.txt，先开始计算。")
            return
        if self.search_worker is not None and self.search_worker.isRunning():
            self.search_worker.cancel()
        self.search_results.setPlainText(f"正在查找 {needle} …")
        self.search_worker = SearchWorker(text_file, needle)
        self.search_worker.finished_results.connect(self._show_search_results)
        self.search_worker.failed.connect(lambda message: self.search_results.setPlainText(f"搜索失败：{message}"))
        self.search_worker.start()

    def _show_search_results(self, results: list) -> None:
        if not results:
            self.search_results.setPlainText("未找到（仅在已写入的位数范围内搜索）。")
            return
        lines = [f"命中 {len(results)} 处（小数位序号，从 1 开始）："]
        lines += [f"  第 {index:,} 位" for index, _ in results]
        self.search_results.setPlainText("\n".join(lines))

    def _run_bbp(self) -> None:
        position = self.bbp_position.value()
        if position > 10_000_000:
            answer = QMessageBox.question(
                self,
                "BBP 成本警告",
                "该位置非常靠后，BBP 校验可能耗时数分钟到数小时。确认继续？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._send(protocol.BbpCheckCommand(position=position, count=self.config.bbp_default_count))

    def _copy_prefix(self) -> None:
        text_file = self.output_dir / "pi.txt"
        if not text_file.exists():
            return
        with open(text_file, "r", encoding="ascii") as handle:
            text = handle.read(COPY_PREFIX_DEFAULT + 1024)
        text = text.replace("\n", "")
        if len(text) > CLIPBOARD_LIMIT:
            QMessageBox.information(self, "复制", "内容超过剪贴板上限，请使用「导出 gzip…」。")
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"已复制前 {len(text):,} 个字符")

    def _export(self) -> None:
        source = self.output_dir / "pi.txt"
        if not source.exists():
            QMessageBox.information(self, "导出", "尚无 pi.txt。")
            return
        target, _ = QFileDialog.getSaveFileName(self, "导出 gzip", str(source) + ".gz", "Gzip (*.gz)")
        if not target:
            return
        self.statusBar().showMessage("正在压缩导出…")
        QApplication.processEvents()
        gzip_export(source, Path(target))
        self.statusBar().showMessage(f"已导出 → {target}")

    # ---------- 关闭 ----------

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.is_alive():
            answer = QMessageBox.question(self, "退出", "计算仍在进行。停止并保存后退出？")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._send(protocol.StopCommand())
            self.worker.join(timeout=15)
        if self.search_worker is not None:
            self.search_worker.cancel()
            self.search_worker.wait(2000)
        event.accept()


def run_app(argv: list[str]) -> int:
    app = QApplication(argv)
    settings_path = Path("settings.json")
    config = load_settings(settings_path)
    apply_theme(app, config.theme)
    window = MainWindow(config, settings_path)
    window.show()
    return app.exec()
```
```
git add pi_tool/app/history.py
git commit -m "feat. 添加会话扫描与历史记录维护"
git add pi_tool/app/search.py
git commit -m "feat. 添加 mmap 数字搜索线程"
git add pi_tool/app/export.py
git commit -m "feat. 添加 gzip 导出"
git add pi_tool/app/main_window.py
git commit -m "feat. 实现主窗口（仪表盘/控制/统计/搜索/BBP/历史/日志/状态机）"
```

- [ ] **Step 2: 离屏冒烟（主窗口可实例化）**

运行：
```
.venv\Scripts\python.exe -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from pathlib import Path; from PySide6.QtWidgets import QApplication; app=QApplication([]); from pi_tool.common.config import Config; from pi_tool.app.main_window import MainWindow; window=MainWindow(Config(), Path('settings.json')); print('main window ok')"
```
预期输出：`main window ok`（在仓库根目录运行；会顺带创建/读取 `settings.json`，属预期，已被 gitignore）。

- [ ] **Step 3: 真机 GUI 冒烟（人工，5 分钟）**

运行：`.venv\Scripts\python.exe -m pi_tool`
按以下清单逐项确认（全部通过才可提交）：
1. 窗口出现，深色主题，右上"切换主题"点击后变浅色、再点回深色；
2. [新计算…] 打开对话框：改目标位数为 `1000000`、输出目录保持默认，点确定 → 进度条开始、速率出现数字、滚动区出现 π 数字；
3. 点击 [暂停]：1~2 秒内按钮状态切换为"暂停态"，`output\pi.txt` 存在且内容以 `3.14159…` 开头；
4. 点击 [继续]（继续会话）：恢复运行；
5. [设置] 把刷新间隔改成 `0.2` 秒：速率刷新更频繁；
6. 完成后状态栏显示 SHA-256；日志页有"完成"记录；
7. 关闭窗口：无异常退出。

- [ ] **Step 4: 全量回归**

运行：`.venv\Scripts\python.exe -m pytest tests -q`
预期：全部通过。

---

### Task 13: 启动脚本、README 与验收演练

**Covers:** [S2], [S9], [S10]

**Files:**
- Create: `run.bat`, `README.md`

**Interfaces:**
- Consumes: 全部
- Produces: 可交付使用说明；README 内嵌实测性能表与参考 SHA-256

- [ ] **Step 1: 写 `run.bat` 并提交**

```bat
@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv，请先执行: py -3.14 -m venv .venv
    echo        然后: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)
".venv\Scripts\python.exe" -m pi_tool
```
```
git add run.bat
git commit -m "chore. 添加 Windows 一键启动脚本"
```

- [ ] **Step 2: 生成 100 万位参考 SHA-256**

运行：
```
.venv\Scripts\python.exe -m pi_tool.engine.worker --output-dir output\ref1m --target-digits 1000000
```
把输出的 `pi.session.json` 中 `sha256_final` 与 `written_digits` 记录下来（写入 README "参考校验值" 一节）。**注意：`output\` 已被 gitignore，不要把 pi.txt 提交进仓库。**

- [ ] **Step 3: 写 `README.md` 并提交**

README 内容（按以下结构填实，性能表用 Task 5 实测数据、校验值用 Step 2 结果）：

```markdown
# PiCalculator — π 实时计算小工具

基于 Chudnovsky 级数 + 二分分裂 + GMP 大数乘法（gmpy2），界面使用 PySide6 的桌面工具：
实时计算 π、滚动显示最新稳定数字、可暂停/保存/续算，结果确定性写入 `pi.txt`。

## 环境要求

- Windows + 64 位 Python 3.14（`py -3.14`）
- 依赖：gmpy2 / PySide6 / psutil（均有预编译 wheel，无需编译器）

## 安装

py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

## 运行 / 测试

run.bat
（或）.venv\Scripts\python.exe -m pi_tool
（测试）.venv\Scripts\python.exe -m pytest tests -q
（基准）.venv\Scripts\python.exe -m scripts.bench

## 功能

- 新计算 / 继续先前计算（检查点秒级恢复；无检查点自动降级重演）
- 实时位数与速率（位/秒、位/分可切换，刷新间隔可调）
- 最新稳定数字滚动显示（绝不显示未稳定数字）
- 暂停 / 立即保存 / 停止（随时可继续，最终文件字节与一次性计算一致）
- 三层校验：权威常数前 1000 位比对、整文件 SHA-256、BBP 十六进制独立抽查
- π 数字搜索、数字频率统计、深/浅主题、内存监控自动暂停、历史会话与 gzip 导出

## 输出文件（输出目录内）

- `pi.txt`：`3.` 开头，每行 1000 位，纯 ASCII，完成后补尾换行
- `pi.session.json`：会话元数据（位数/状态/统计/SHA-256）
- `pi.checkpoint.bin`：可恢复的计算状态（原子写入）
- `pi.log`：运行日志

## 实测性能（i5-11300H，本机实测，<填 Task 5 数据>）

| 目标位数 | 耗时 | pi.txt | 检查点 |
|---|---|---|---|
| 100 万 | … | ~1 MB | ~1.2 MB |
| 1000 万 | … | ~10 MB | ~12 MB |
| 1 亿 | 未实测（按上述标度外推） | ~100 MB | ~125 MB |

## 参考校验值

- 100 万位完成：`written_digits = <Step 2 值>`，`sha256_final = <Step 2 值>`
  （重跑同一目标应得到完全相同的值）

## 已知限制

- BBP 校验在超大位置会长时间占用 worker（其间不能暂停）；默认 10^7 位以内
- 完成时写入的是"全部稳定位"，通常比目标位数多几十位（对同一目标恒为同一值）
- 单线程计算；多进程并行、C++ 引擎、exe 打包列为后续版本
```
```
git add README.md
git commit -m "docs. 添加安装/运行/功能/性能与校验说明"
```

- [ ] **Step 4: 完整验收演练（自动 + 人工，按 spec [S10] 逐条勾选）**

1. `.venv\Scripts\python.exe -m pytest tests -q` 全绿；
2. 10 万位任务：暂停→关程序→重启→继续 → 文件与一次性完成字节相同（e2e 已自动覆盖；再人工走一遍 UI 路径）；
3. 1000 万位任务运行中 UI 可操作、无假死；速率单位切换正确；数字持续滚动；
4. 同一目标位数重跑一次，SHA-256 相同；
5. 把内存阈值临时调到 0.5 GB → 触发自动暂停并提示（10 万位任务即可复现）；
6. BBP 校验在位置 1,000,000 跑通并显示对照窗口；
7. 搜索一个已知存在的短串（例如 "141592"）能定位到第 1 位起；
8. 导出 gzip 后用 7-Zip/资源管理器解压，与原 `pi.txt` 一致。

- [ ] **Step 5: 收尾提交**

```
git status --short
git add <如有遗漏的验收改动>
git commit -m "chore. 完成 v1 验收演练记录与收尾"
```

---

## 计划自检记录（写计划时执行）

- **规格覆盖**：[S1]→Task 12；[S2]→Task 5/13；[S3]→全局约束与任务边界；[S4]→Task 3/4；[S5]→Task 6/10；[S6]→Task 9/10/12；[S7]→Task 11/12；[S8]→Task 2/7/8/12；[S9]→Task 1/13；[S10]→各任务测试步骤 + Task 13；[S11]→Task 6/10 的原子写与内存检查。无遗漏。
- **占位符扫描**：无 TBD/TODO；唯一"数据填充"处（`PI_FIRST_1000`、README 实测表、参考 SHA-256）都给出了精确生成命令与断言。
- **类型/命名一致性**：`SeriesState.triple`、`pi_prefix_decimal/hex`、`ProgressEvent/PausedEvent/SavedEvent/DoneEvent/BbpResultEvent/ErrorEvent/LogEvent`、`spawn_worker(...)`、`stable_digits_for_terms/terms_for_digits`、`CheckpointError`、`NotEnoughTerms` 全文一致。
- **已知偏差（相对 spec 的工程细化，行为不变）**：① worker 启动参数经进程参数传递而非 start/resume 命令；② BBP 校验不做中途取消（spec 未要求）；③ 完成时写出的稳定位可能比目标多几十位（由稳定位数公式决定、确定性不变），README 已注明。

