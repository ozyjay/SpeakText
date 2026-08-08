SHELL := /usr/bin/pwsh
.SHELLFLAGS := -NoLogo -NoProfile -NonInteractive -Command

.PHONY: check build run run-installed install-user uninstall-user test

check:
	./scripts/bootstrap.ps1 -Check

build:
	./scripts/bootstrap.ps1

run:
	Write-Host 'Running the development checkout.'; $$env:PYTHONPATH = 'src'; $$env:SPEAKTEXT_WORKER = 'build/speaktext-worker'; python3 -m speaktext

run-installed:
	./scripts/run-installed.ps1

install-user: build
	./scripts/install-user.ps1

uninstall-user:
	./scripts/uninstall-user.ps1

test:
	$$env:PYTHONDONTWRITEBYTECODE = '1'; $$env:PYTHONPATH = 'src'; python3 -m unittest discover -s tests -v
