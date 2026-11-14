PY := .venv/bin/python
NBA := .venv/bin/nba

.PHONY: setup synth readiness run web serve demo test

setup:            ## create the Python environment and install the engine and the web app
	uv venv .venv
	uv pip install --python $(PY) -e ".[dev]"
	cd web && npm ci

synth:            ## generate the synthetic datasets into data/
	$(NBA) synth

readiness:        ## print the data readiness report
	$(NBA) readiness

run:              ## run the 26-week pilot (engine in test territories, today's plan in control)
	$(NBA) run --weeks 26

web:              ## build the web app (served by the engine at http://127.0.0.1:8000)
	cd web && npm run build

serve:            ## start the engine's API and the web app
	$(NBA) serve

demo: synth web   ## fresh data, rule versions and studio-written rules, then the app; run the pilot from the Feedback and Results screens
	rm -f data/rule_versions.json data/custom_rules.json
	$(NBA) serve

test:             ## run the automated tests
	$(PY) -m pytest -q
