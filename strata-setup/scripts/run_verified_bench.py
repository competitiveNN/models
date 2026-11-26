
import json, urllib.request

url = "http://127.0.0.1:1235/v1/chat/completions"
prompts = [
    ("short", "What is 2+2?", 32),
    ("medium", "Explain gravity in one sentence.", 48),
]

results = []
for name, prompt, mt in prompts:
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": mt}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as res:
        d = json.loads(res.read().decode())
        t = d.get("timings", {})
        results.append({
            "case": name,
            "prompt_tokens": t.get("prompt_n"),
            "prompt_per_second": t.get("prompt_per_second"),
            "predicted_tokens": t.get("predicted_n"),
            "predicted_per_second": t.get("predicted_per_second"),
            "draft_accepted": t.get("draft_n_accepted"),
            "draft_n": t.get("draft_n"),
        })

with open("runs/verified-run.json", "w") as f:
    json.dump({"verified_results": results}, f, indent=2)
print("SUCCESS:", results)
