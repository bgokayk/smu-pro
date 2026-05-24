import json
from pathlib import Path

cfg_path = Path(r"C:\Users\User\.codex\smu-pro\smu_config.json")
bak = cfg_path.with_suffix(".json.bak_before_apikey")
if not bak.exists():
    bak.write_text(cfg_path.read_text(encoding="utf-8-sig"), encoding="utf-8")
    print(f"Yedek alindi: {bak.name}")

cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
cfg["deepseek_api_key"] = "sk-5d6a12d37ffb4ef988e99a29bae7ba47"
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"smu-pro API key yazildi. Uzunluk: {len(cfg['deepseek_api_key'])}")
