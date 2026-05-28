.PHONY: install lint test run clean

install:
	pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

test:
	pytest tests/ -v --tb=short

run:
	uvicorn lpi.main:app --reload --port 8000

clean:
	python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
