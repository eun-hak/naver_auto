import sys
from export_body_4500_samples import TOP4, OUT_DIR, ROOT, generate, slug

spec = next(m for m in TOP4 if m.id == "llama-3.1-8b-instant")
r = generate(spec)
if not r.get("ok"):
    print("FAIL", r.get("error"))
    sys.exit(1)
path = OUT_DIR / f"{slug(spec.id)}.md"
meta = f"<!-- groq max_tokens=4096 | chars: {r['content_len']} | elapsed: {r['elapsed_sec']}s -->\n\n"
path.write_text(meta + r["content"], encoding="utf-8")
print(f"OK {r['content_len']} chars [{('target OK' if r['in_target_len'] else 'under target')}] -> {path.relative_to(ROOT)}")
