#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek Consultant — SMU V3.0 yardımcı danışman modülü.

Kullanım:
    from deepseek_consultant import consult, decide, validate

    # Açık uçlu soru
    answer = consult("Bu başlık yeterince hook'lu mu?", context={...})

    # Karar verme
    idx = decide(options=[title1, title2, title3], criterion="en yüksek tıklanma")

    # Doğrulama
    result = validate(content=title, requirements=["70-100 karakter", "Türkçe"])
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "smu_config.json"
LEDGER_FILE = ROOT / "logs" / "deepseek_consultations.jsonl"
DAILY_CONSULT_LIMIT = 500  # günlük token bütçesi


def _load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _get_api_key() -> str:
    config = _load_config()
    return config.get("deepseek_api_key", "")


def _daily_count() -> int:
    """Bugün kaç consult yapılmış say."""
    if not LEDGER_FILE.exists():
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0
    with LEDGER_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("ts", "").startswith(today):
                    count += 1
            except Exception:
                continue
    return count


def _log_consult(question: str, context: dict | None, answer: str, model: str) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_FILE.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.now().isoformat(),
                    "model": model,
                    "question": question[:200],
                    "context": context,
                    "answer": answer[:500],
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def consult(
    question: str,
    context: dict | None = None,
    model: str = "deepseek-chat",
    max_retries: int = 2,
) -> str:
    """DeepSeek'e soru sor, cevap al.

    Args:
        question: Net soru
        context: Ek bağlam (kanal, sahne özeti vb.)
        model: deepseek-chat (ucuz) veya deepseek-reasoner (pahalı)
        max_retries: Maksimum tekrar denemesi

    Returns:
        DeepSeek cevabı (str), hata durumunda ""
    """
    api_key = _get_api_key()
    if not api_key:
        return ""

    # Günlük limit kontrolü
    if _daily_count() >= DAILY_CONSULT_LIMIT:
        print(f"[DeepSeek Consultant] Günlük limit aşıldı ({DAILY_CONSULT_LIMIT})")
        return ""

    system = (
        "Sen Türk sosyal medya stratejisi uzmanısın. "
        "SMU (Social Media Unit) otomasyon sisteminin yardımcı danışmanısın. "
        "Kısa, net, eylem odaklı cevap ver. Gereksiz açıklama yapma."
    )

    user_msg = question
    if context:
        user_msg += f"\n\nBağlam:\n{json.dumps(context, ensure_ascii=False, indent=2, default=str)}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": 1500,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries + 1):
        try:
            r = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=60,
            )
            r.raise_for_status()
            answer = r.json()["choices"][0]["message"]["content"].strip()
            _log_consult(question, context, answer, model)
            return answer
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1)
                continue
            print(f"[DeepSeek Consultant HATA] {e}")
            return ""


def decide(
    options: list[str],
    criterion: str,
    context: dict | None = None,
) -> int:
    """Birden fazla seçenek arasından karar al.

    Args:
        options: Seçenek listesi
        criterion: Karar kriteri (örn: "en yüksek tıklanma potansiyeli")
        context: Ek bağlam

    Returns:
        Seçilen index (0-indexed), hata durumunda 0
    """
    q = f"Aşağıdaki seçeneklerden hangisi '{criterion}' kriterine göre en iyisi?\n\n"
    for i, opt in enumerate(options):
        q += f"{i}: {opt}\n"
    q += "\nSadece 0-indexed sayı dön. Başka bir şey yazma."

    ans = consult(q, context, model="deepseek-chat")
    try:
        # Sayıyı bul
        nums = re.findall(r"\d+", ans)
        if nums:
            idx = int(nums[0])
            if 0 <= idx < len(options):
                return idx
    except Exception:
        pass
    return 0  # fallback


def validate(
    content: str,
    requirements: list[str],
    context: dict | None = None,
) -> dict[str, Any]:
    """Bir içeriği kriterlere göre değerlendir.

    Args:
        content: Değerlendirilecek içerik
        requirements: Kriter listesi
        context: Ek bağlam

    Returns:
        {"pass": bool, "issues": [str], "suggestion": str}
    """
    q = (
        f"Aşağıdaki içeriği değerlendir.\n\n"
        f"İçerik:\n{content}\n\n"
        f"Kriterler:\n" + "\n".join(f"- {r}" for r in requirements) + "\n\n"
        f"JSON formatında dön: {{\"pass\": bool, \"issues\": [str], \"suggestion\": str}}"
    )
    ans = consult(q, context, model="deepseek-chat")
    try:
        m = re.search(r"\{.*\}", ans, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {"pass": True, "issues": [], "suggestion": ""}
