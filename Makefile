PY := .venv/bin/python
NBA := .venv/bin/nba

.PHONY: setup synth readiness test

setup:            ## create the Python environment and install the engine
	uv venv .venv
	uv pip install --python $(PY) -e ".[dev]"

synth:            ## generate the synthetic datasets into data/
	$(NBA) synth

readiness:        ## print the data readiness report
	$(NBA) readiness

test:             ## run the automated tests
	$(PY) -m pytest -q
