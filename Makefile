PY ?= python3
export PYTHONPATH := src

install:        ## install all dependencies
	$(PY) -m pip install torch --index-url https://download.pytorch.org/whl/cpu
	$(PY) -m pip install -r requirements.txt

evaluate:       ## generate data, train, evaluate, write artifacts + reports
	$(PY) -m confluence.evaluation.run

dashboard:      ## run the Streamlit dashboard (demo mode if no database)
	streamlit run dashboard/app.py

api:
	uvicorn confluence.api.main:app --port 8000

test:
	$(PY) -m pytest -q

stack:          ## full Kafka + TimescaleDB pipeline
	docker compose up --build

study-report:   ## analyse user-study responses (H3)
	$(PY) -m confluence.evaluation.user_study

diagram:
	$(PY) scripts/make_architecture.py
