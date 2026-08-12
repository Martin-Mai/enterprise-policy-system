#!/usr/bin/env python3
"""
半自动化生成 RAGAS 评测用例（阶段 2 数据层）。

流程：
  1. 从 test_datasets/ 提取目录/章节/摘要
  2. 调用 Ollama 批量生成 QA 草稿
  3. 去重过滤 → drafts_100.jsonl / filtered_80.jsonl
  4. 合并 golden 补充 + 人工 low 拒答 → ragas_cases.jsonl（50 条）

用法（仓库根目录或 eval/ 目录）：
    python eval/generate_cases.py --config eval/config.yaml
    python eval/generate_cases.py --draft-only
    python eval/generate_cases.py --finalize
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx
import yaml
from tqdm import tqdm

EVAL_DIR = Path(__file__).resolve().parent

REFUSAL_GROUND_TRUTH = "未找到相关信息。"

MANUAL_REFUSAL_CASES: List[Dict[str, Any]] = [
    {
        "question": "公司食堂今天午餐有哪些菜品？",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "特斯拉（Tesla）最新股价是多少？",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "请用 Python 写一个快速排序算法并解释时间复杂度。",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "今天上海天气怎么样，适合出门吗？",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "帮我写一首关于春天的七言绝句。",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "比特币当前美元价格是多少？",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "推荐公司附近评分最高的火锅店。",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "如何绕过公司防火墙访问被屏蔽的网站？",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "集团 CEO 的个人手机号是多少？",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
    {
        "question": "2024 年巴黎奥运会金牌榜第一名是哪个国家？",
        "tier": "low",
        "expected_files": [],
        "must_contain_in_context": [],
        "ground_truth": REFUSAL_GROUND_TRUTH,
        "should_refuse": True,
        "source_doc": None,
    },
]


def resolve_config_path(arg: str | None) -> Path:
    candidates: List[Path] = []
    if arg:
        p = Path(arg)
        candidates.append(p if p.is_absolute() else Path.cwd() / p)
        if not candidates[-1].exists():
            candidates.append(EVAL_DIR / arg)
    else:
        candidates.extend(
            [
                Path.cwd() / "eval" / "config.yaml",
                Path.cwd() / "config.yaml",
                EVAL_DIR / "config.yaml",
            ]
        )
    for path in candidates:
        if path.exists():
            return path.resolve()
    raise FileNotFoundError(f"找不到配置文件，已尝试: {[str(p) for p in candidates]}")


def resolve_eval_path(eval_dir: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        return path
    return (eval_dir / path).resolve()


def setup_server_imports(server_env_path: Path) -> None:
    server_dir = server_env_path.parent.resolve()
    server_str = str(server_dir)
    if server_str not in sys.path:
        sys.path.insert(0, server_str)
    from dotenv import load_dotenv

    if server_env_path.exists():
        load_dotenv(dotenv_path=server_env_path, override=True)


def load_config(config_path: Path) -> Tuple[Path, Dict[str, Any]]:
    eval_dir = config_path.parent
    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return eval_dir, raw


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_question(text: str) -> str:
    cleaned = re.sub(r"\s+", "", text.strip().lower())
    cleaned = re.sub(r"[？?！!。．,，、；;：:\"'\"()（）\[\]【】]", "", cleaned)
    return cleaned


def list_test_documents(test_dir: Path) -> List[Path]:
    docs: List[Path] = []
    for path in sorted(test_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".pdf", ".md"}:
            continue
        if path.name.startswith("."):
            continue
        docs.append(path)
    return docs


def extract_doc_profile(
    file_path: Path,
    parse_pdf,
    parse_markdown,
) -> Dict[str, Any]:
    file_name = file_path.name
    if file_path.suffix.lower() == ".pdf":
        segments = parse_pdf(str(file_path))
    else:
        segments = parse_markdown(str(file_path))

    sections: List[str] = []
    seen: Set[str] = set()
    for seg in segments:
        title = str(seg.get("section_title", "")).strip()
        if title and title not in seen:
            seen.add(title)
            sections.append(title)

    full_text = "\n".join(str(seg.get("text", "")) for seg in segments)
    summary = re.sub(r"\s+", " ", full_text).strip()[:700]

    return {
        "file_name": file_name,
        "sections": sections[:20],
        "toc": sections[:12],
        "summary": summary,
        "segment_count": len(segments),
    }


def sanitize_json_text(text: str) -> str:
    """移除 JSON 非法控制字符，避免 LLM 输出含 raw newline 导致解析失败。"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)


def extract_json_array(text: str) -> List[Dict[str, Any]]:
    text = sanitize_json_text(text.strip())
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("响应中未找到 JSON 数组")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, list):
        raise ValueError("JSON 顶层应为数组")
    return payload


def call_ollama_generate(
    *,
    url: str,
    model: str,
    prompt: str,
    timeout: float,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4},
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    return str(data.get("response", "")).strip()


def build_generation_prompt(profile: Dict[str, Any], count: int) -> str:
    sections_text = "\n".join(f"- {s}" for s in profile["toc"]) or "（无章节标题）"
    return textwrap.dedent(
        f"""
        你是企业知识库评测数据标注员。请仅依据下列文档信息生成 {count} 条中文问答评测用例。

        【文档文件名】{profile["file_name"]}
        【章节目录】
        {sections_text}

        【内容摘要】
        {profile["summary"]}

        输出要求：
        1. 只输出 JSON 数组，不要其他说明。
        2. 每条字段：question, tier, expected_files, must_contain_in_context, ground_truth
        3. tier 只能是 high 或 medium（不要 low）
        4. expected_files 必须是 ["{profile["file_name"]}"]
        5. must_contain_in_context：2~4 个必须能在文档正文中找到的关键词或短语
        6. ground_truth：1~3 句参考答案，基于文档事实，不要编造
        7. high：考察精确数字/名称/阈值；medium：考察流程/定义/范围类问题
        8. question 长度不少于 12 个汉字，彼此不要重复

        示例格式：
        [
          {{
            "question": "...?",
            "tier": "high",
            "expected_files": ["{profile["file_name"]}"],
            "must_contain_in_context": ["关键词1", "关键词2"],
            "ground_truth": "..."
          }}
        ]
        """
    ).strip()


def normalize_draft(raw: Dict[str, Any], known_files: Set[str]) -> Optional[Dict[str, Any]]:
    question = str(raw.get("question", "")).strip()
    tier = str(raw.get("tier", "")).strip().lower()
    if tier not in {"high", "medium"}:
        return None
    if len(question) < 12:
        return None

    expected = raw.get("expected_files") or []
    if isinstance(expected, str):
        expected = [expected]
    expected = [str(f).strip() for f in expected if str(f).strip()]
    if not expected or any(f not in known_files for f in expected):
        return None

    must_contain = raw.get("must_contain_in_context") or []
    if isinstance(must_contain, str):
        must_contain = [must_contain]
    must_contain = [str(k).strip() for k in must_contain if str(k).strip()]
    if len(must_contain) < 1:
        return None

    ground_truth = str(raw.get("ground_truth", "")).strip()
    if len(ground_truth) < 8:
        return None

    return {
        "question": question,
        "tier": tier,
        "expected_files": expected,
        "must_contain_in_context": must_contain,
        "ground_truth": ground_truth,
        "should_refuse": False,
        "source_doc": expected[0],
        "origin": "llm",
    }


def filter_drafts(
    drafts: List[Dict[str, Any]],
    *,
    known_files: Set[str],
    target_count: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    seen: Set[str] = set()
    accepted: List[Dict[str, Any]] = []
    stats = {
        "input": len(drafts),
        "too_short": 0,
        "duplicate": 0,
        "bad_tier": 0,
        "bad_files": 0,
        "bad_must_contain": 0,
        "bad_ground_truth": 0,
    }

    for raw in drafts:
        question = str(raw.get("question", "")).strip()
        norm = normalize_question(question)
        if len(question) < 12:
            stats["too_short"] += 1
            continue
        if norm in seen:
            stats["duplicate"] += 1
            continue

        tier = str(raw.get("tier", "")).strip().lower()
        if tier not in {"high", "medium"}:
            stats["bad_tier"] += 1
            continue

        expected = raw.get("expected_files") or []
        if isinstance(expected, str):
            expected = [expected]
        expected = [str(f).strip() for f in expected if str(f).strip()]
        if not expected or any(f not in known_files for f in expected):
            stats["bad_files"] += 1
            continue

        must_contain = raw.get("must_contain_in_context") or []
        if isinstance(must_contain, str):
            must_contain = [must_contain]
        must_contain = [str(k).strip() for k in must_contain if str(k).strip()]
        if not must_contain:
            stats["bad_must_contain"] += 1
            continue

        ground_truth = str(raw.get("ground_truth", "")).strip()
        if len(ground_truth) < 8:
            stats["bad_ground_truth"] += 1
            continue

        seen.add(norm)
        accepted.append(
            {
                **raw,
                "question": question,
                "tier": tier,
                "expected_files": expected,
                "must_contain_in_context": must_contain,
                "ground_truth": ground_truth,
                "should_refuse": False,
                "source_doc": expected[0],
                "origin": raw.get("origin", "llm"),
            }
        )

    high = [r for r in accepted if r["tier"] == "high"]
    medium = [r for r in accepted if r["tier"] == "medium"]
    balanced: List[Dict[str, Any]] = []
    hi_idx = med_idx = 0
    while len(balanced) < target_count and (hi_idx < len(high) or med_idx < len(medium)):
        if hi_idx < len(high):
            balanced.append(high[hi_idx])
            hi_idx += 1
            if len(balanced) >= target_count:
                break
        if med_idx < len(medium):
            balanced.append(medium[med_idx])
            med_idx += 1

    if len(balanced) < target_count:
        rest = high[hi_idx:] + medium[med_idx:]
        for row in rest:
            if len(balanced) >= target_count:
                break
            if row not in balanced:
                balanced.append(row)

    stats["accepted"] = len(accepted)
    stats["output"] = len(balanced)
    stats["high"] = sum(1 for r in balanced if r["tier"] == "high")
    stats["medium"] = sum(1 for r in balanced if r["tier"] == "medium")
    return balanced[:target_count], stats


def load_golden_queries(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def golden_to_ragas(row: Dict[str, Any]) -> Dict[str, Any]:
    keywords = row.get("must_contain_in_context") or []
    if keywords:
        joined = "、".join(keywords)
        ground_truth = f"根据知识库文档，相关要点包括：{joined}。"
    else:
        ground_truth = REFUSAL_GROUND_TRUTH
    return {
        "question": row["question"],
        "tier": row.get("tier", "medium"),
        "expected_files": row.get("expected_files") or [],
        "must_contain_in_context": keywords,
        "ground_truth": ground_truth,
        "should_refuse": bool(row.get("should_refuse")),
        "source_doc": (row.get("expected_files") or [None])[0],
        "origin": "golden",
        "golden_id": row.get("id"),
    }


def pick_tier_pool(
    pool: List[Dict[str, Any]],
    tier: str,
    need: int,
    seen: Set[str],
) -> Tuple[List[Dict[str, Any]], int]:
    picked: List[Dict[str, Any]] = []
    for row in pool:
        if row.get("tier") != tier:
            continue
        norm = normalize_question(row["question"])
        if norm in seen:
            continue
        picked.append(row)
        seen.add(norm)
        if len(picked) >= need:
            break
    return picked, need - len(picked)


def finalize_ragas_cases(
    filtered: List[Dict[str, Any]],
    golden_path: Path,
    tier_ratio: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    need_high = int(tier_ratio.get("high", 20))
    need_medium = int(tier_ratio.get("medium", 20))
    need_low = int(tier_ratio.get("low", 10))

    llm_pool = list(filtered)
    golden_rows = [
        golden_to_ragas(g)
        for g in load_golden_queries(golden_path)
        if not g.get("should_refuse")
    ]

    seen: Set[str] = set()
    selected_high, short_high = pick_tier_pool(llm_pool, "high", need_high, seen)
    selected_medium, short_medium = pick_tier_pool(llm_pool, "medium", need_medium, seen)

    golden_supplemented = 0
    if short_high > 0:
        extra, short_high = pick_tier_pool(golden_rows, "high", short_high, seen)
        selected_high.extend(extra)
        golden_supplemented += len(extra)
    if short_medium > 0:
        extra, short_medium = pick_tier_pool(golden_rows, "medium", short_medium, seen)
        selected_medium.extend(extra)
        golden_supplemented += len(extra)

    if short_high > 0 or short_medium > 0:
        print(
            f"[warn] high/medium 仍不足：high 缺 {short_high}，medium 缺 {short_medium}。"
            "请检查 drafts 质量或 golden_queries 覆盖。"
        )

    manual_low = MANUAL_REFUSAL_CASES[:need_low]
    if len(manual_low) < need_low:
        raise RuntimeError(f"人工拒答样本不足 {need_low} 条")

    final_rows = selected_high + selected_medium + manual_low
    for idx, row in enumerate(final_rows, start=1):
        row["id"] = f"rc{idx:03d}"
        row.pop("golden_id", None)

    meta = {
        "llm_high_selected": sum(
            1 for r in selected_high if r.get("origin") != "golden"
        ),
        "llm_medium_selected": sum(
            1 for r in selected_medium if r.get("origin") != "golden"
        ),
        "golden_supplemented": golden_supplemented,
        "manual_low": len(manual_low),
        "total": len(final_rows),
        "tier_counts": {
            "high": sum(1 for r in final_rows if r.get("tier") == "high"),
            "medium": sum(1 for r in final_rows if r.get("tier") == "medium"),
            "low": sum(1 for r in final_rows if r.get("tier") == "low"),
        },
        "refusal_count": sum(1 for r in final_rows if r.get("should_refuse")),
    }
    return final_rows, meta


def generate_drafts_with_llm(
    profiles: List[Dict[str, Any]],
    *,
    draft_count: int,
    ollama_url: str,
    ollama_model: str,
    timeout: float,
) -> List[Dict[str, Any]]:
    if not profiles:
        return []

    per_doc = max(1, draft_count // len(profiles))
    remainder = draft_count - per_doc * len(profiles)

    all_drafts: List[Dict[str, Any]] = []
    known_files = {p["file_name"] for p in profiles}

    for index, profile in enumerate(tqdm(profiles, desc="LLM 生成草稿", unit="doc")):
        count = per_doc + (1 if index < remainder else 0)
        prompt = build_generation_prompt(profile, count)
        raw_items: List[Dict[str, Any]] = []
        for attempt in range(2):
            try:
                response = call_ollama_generate(
                    url=ollama_url,
                    model=ollama_model,
                    prompt=prompt,
                    timeout=timeout,
                )
                raw_items = extract_json_array(response)
                break
            except Exception as exc:
                if attempt == 0:
                    continue
                print(f"[warn] {profile['file_name']} 生成失败: {exc}")

        for item in raw_items:
            normalized = normalize_draft(item, known_files)
            if normalized:
                all_drafts.append(normalized)
            if len(all_drafts) >= draft_count:
                break
        if len(all_drafts) >= draft_count:
            break
        time.sleep(0.3)

    return all_drafts[:draft_count]


def resolve_ollama_settings(cfg: Dict[str, Any]) -> Tuple[str, str, float]:
    from app.core.config import settings

    url = cfg.get("ollama_generate_url") or settings.OLLAMA_GENERATE_URL
    model = cfg.get("ollama_model") or settings.OLLAMA_CHAT_MODEL
    timeout = float(cfg.get("ollama_timeout", settings.OLLAMA_GENERATE_TIMEOUT))
    return url, model, timeout


def run_draft_pipeline(cfg: Dict[str, Any], eval_dir: Path) -> Dict[str, Any]:
    setup_server_imports(resolve_eval_path(eval_dir, cfg["server_env_path"]))
    from app.services.document_processor import parse_markdown, parse_pdf

    test_dir = resolve_eval_path(eval_dir, cfg["test_datasets_path"])
    drafts_path = resolve_eval_path(eval_dir, cfg["drafts_path"])
    filtered_path = resolve_eval_path(eval_dir, cfg["filtered_path"])

    draft_count = int(cfg.get("draft_count", 100))
    filtered_count = int(cfg.get("filtered_count", 80))

    doc_paths = list_test_documents(test_dir)
    known_files = {p.name for p in doc_paths}
    profiles = [
        extract_doc_profile(path, parse_pdf, parse_markdown) for path in doc_paths
    ]

    ollama_url, ollama_model, timeout = resolve_ollama_settings(cfg)
    drafts = generate_drafts_with_llm(
        profiles,
        draft_count=draft_count,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        timeout=timeout,
    )

    for idx, row in enumerate(drafts, start=1):
        row["draft_id"] = f"draft_{idx:03d}"

    write_jsonl(drafts_path, drafts)
    filtered, filter_stats = filter_drafts(
        drafts,
        known_files=known_files,
        target_count=filtered_count,
    )
    write_jsonl(filtered_path, filtered)

    return {
        "drafts_written": len(drafts),
        "filtered_written": len(filtered),
        "filter_stats": filter_stats,
        "drafts_path": str(drafts_path),
        "filtered_path": str(filtered_path),
    }


def run_finalize_pipeline(cfg: Dict[str, Any], eval_dir: Path) -> Dict[str, Any]:
    filtered_path = resolve_eval_path(eval_dir, cfg["filtered_path"])
    drafts_path = resolve_eval_path(eval_dir, cfg["drafts_path"])
    ragas_path = resolve_eval_path(eval_dir, cfg["ragas_dataset_path"])
    golden_path = resolve_eval_path(
        eval_dir, cfg.get("golden_queries_path", "datasets/golden_queries.json")
    )

    filtered = read_jsonl(filtered_path)
    if not filtered and drafts_path.exists():
        setup_server_imports(resolve_eval_path(eval_dir, cfg["server_env_path"]))
        test_dir = resolve_eval_path(eval_dir, cfg["test_datasets_path"])
        known_files = {p.name for p in list_test_documents(test_dir)}
        filtered, _ = filter_drafts(
            read_jsonl(drafts_path),
            known_files=known_files,
            target_count=int(cfg.get("filtered_count", 80)),
        )
        write_jsonl(filtered_path, filtered)

    tier_ratio = cfg.get("tier_ratio") or {"high": 20, "medium": 20, "low": 10}
    final_rows, meta = finalize_ragas_cases(filtered, golden_path, tier_ratio)
    expected_total = int(cfg.get("final_count", 50))
    if len(final_rows) != expected_total:
        raise RuntimeError(
            f"ragas_cases 条数应为 {expected_total}，实际 {len(final_rows)}"
        )
    if meta["refusal_count"] != tier_ratio.get("low", 10):
        raise RuntimeError("low tier 拒答条数不符合 tier_ratio.low")

    write_jsonl(ragas_path, final_rows)
    meta["ragas_path"] = str(ragas_path)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="半自动化生成 RAGAS 评测用例")
    parser.add_argument("--config", default=None, help="config.yaml 路径")
    parser.add_argument(
        "--draft-only",
        action="store_true",
        help="仅生成 drafts_100.jsonl 与 filtered_80.jsonl",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="仅执行过滤结果合并为 ragas_cases.jsonl",
    )
    args = parser.parse_args()

    config_path = resolve_config_path(args.config)
    eval_dir, cfg = load_config(config_path)

    summary: Dict[str, Any] = {"config": str(config_path)}

    if args.finalize and not args.draft_only:
        summary["finalize"] = run_finalize_pipeline(cfg, eval_dir)
    elif args.draft_only:
        summary["draft"] = run_draft_pipeline(cfg, eval_dir)
    else:
        summary["draft"] = run_draft_pipeline(cfg, eval_dir)
        summary["finalize"] = run_finalize_pipeline(cfg, eval_dir)

    print("\n=== generate_cases 完成 ===")
    if "draft" in summary:
        d = summary["draft"]
        fs = d.get("filter_stats", {})
        print(f"LLM 草稿: {d['drafts_written']} 条 → {d['drafts_path']}")
        print(
            f"过滤后: {d['filtered_written']} 条 → {d['filtered_path']} "
            f"(high={fs.get('high', '?')}, medium={fs.get('medium', '?')})"
        )
    if "finalize" in summary:
        f = summary["finalize"]
        print(f"ragas_cases: {f['total']} 条 → {f['ragas_path']}")
        print(
            f"  LLM high={f['llm_high_selected']}, medium={f['llm_medium_selected']}, "
            f"golden 补充={f['golden_supplemented']}, 人工拒答 low={f['manual_low']}"
        )
        print(f"  tier 分布: {f['tier_counts']}, should_refuse={f['refusal_count']}")


if __name__ == "__main__":
    main()
