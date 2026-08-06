.PHONY: check build run install-user uninstall-user test

check:
	./scripts/bootstrap.sh --check

build:
	./scripts/bootstrap.sh

run:
	PYTHONPATH=src SPEAKTEXT_WORKER=build/speaktext-worker python3 -m speaktext

install-user: build
	./scripts/install-user.sh

uninstall-user:
	./scripts/uninstall-user.sh

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
