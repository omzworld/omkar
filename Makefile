PY := .venv/bin/python
NBA := .venv/bin/nba

.PHONY: setup synth readiness run test

setup:            ## create the Python environment and install the engine
	uv venv .venv
	uv pip install --python $(PY) -e ".[dev]"

synth:            ## generate the synthetic datasets into data/
	$(NBA) synth

readiness:        ## print the data readiness report
	$(NBA) readiness

run:              ## run the 26-week pilot (engine in test territories, today's plan in control)
	$(NBA) run --weeks 26

test:             ## run the automated tests
	$(PY) -m pytest -q
