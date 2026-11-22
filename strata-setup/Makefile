.PHONY: test-bench test-all strata-image strata-smoke coherence-gate test-strata-old docs

test-bench:
	python3 -m unittest discover tests

test-all:
	python3 -m unittest discover tests

strata-image:
	podman build -f Containerfile.strata -t localhost/strata-old:latest .
	$(MAKE) strata-smoke

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

bench-baseline:
	python3 scripts/bench-automation.py --baseline

bench-compare:
	python3 scripts/bench-automation.py --compare --threshold 0.15

bench-report:
	python3 scripts/bench-automation.py --report
