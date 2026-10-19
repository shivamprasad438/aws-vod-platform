.PHONY: install test lint run sample demo up

install:
	pip install -r requirements-dev.txt

test:
	pytest -q

lint:
	ruff check app tests

run:
	uvicorn app.main:app --reload

sample:
	./scripts/make_sample_video.sh sample.mp4

demo:
	./scripts/demo.sh sample.mp4

up:
	docker compose up --build
