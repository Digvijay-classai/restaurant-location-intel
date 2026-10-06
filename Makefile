.PHONY: install test run validate demo-data live-data

install:            ## exact tested versions + dev tools
	pip install -r requirements.lock

test:
	python -m pytest -q

run:
	streamlit run app.py

validate:           ## check committed snapshots
	python scripts/validate_snapshots.py

demo-data:          ## SYNTHETIC snapshots (keeps any LIVE snapshot)
	python scripts/build_demo_data.py

live-data:          ## e.g. make live-data CITY=madrid
	python scripts/pull_live_data.py $(CITY)
