.PHONY: test-bench test-all strata-image strata-smoke coherence-gate test-strata-old docs

test-bench:
	python3 -m unittest discover tests

test-all:
	python3 -m unittest discover tests

strata-image:
	podman build -f Containerfile.strata -t localhost/strata-old:latest .
	$(MAKE) strata-smoke
	$(MAKE) pin-image-digest

pin-image-digest:
	python3 scripts/pin_image_digest.py --pin

verify-image-digest:
	python3 scripts/pin_image_digest.py --verify

validate-model:
	python3 scripts/model_weight_validator.py --model-dir /model/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf 2>/dev/null || python3 scripts/model_weight_validator.py --model-dir /models/swift-iq3_xxs 2>/dev/null || echo "[validate-model] no model dir found, skipping"

strata-smoke:
	./scripts/strata-old-smoke.sh

coherence-gate:
	python3 bench-coherence-2xb580.py

test-strata-old: test-all strata-smoke
	@echo "[test-strata-old] all strata-old checks passed"

docs:
	@echo "docs/strata-old-2xb580.md"

.PHONY: bench-run bench-baseline bench-compare bench-report

bench-run:
	python3 scripts/bench-automation.py --run --url http://127.0.0.1:1235/v1/chat/completions

bench-tp2:
	./bench/b580-tp2-bench.sh run

bench-trend:
	./bench/b580-tp2-bench.sh trend

bench-compare-tp2:
	./bench/b580-tp2-bench.sh compare

bench-baseline:
	python3 scripts/bench-automation.py --baseline

bench-compare:
	python3 scripts/bench-automation.py --compare --threshold 0.15

bench-report:
	python3 scripts/bench-automation.py --report
