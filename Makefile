#Dockerfile vars

#vars

.PHONY: help build upload upload-check install install-dev docs all

PYTHON ?= python3
TWINE := $(shell command -v twine 2>/dev/null)

ifeq ($(TWINE),)
TWINE := nix shell nixpkgs\#twine --command twine
endif

PACKAGE_VERSION := $(shell $(PYTHON) setup.py --version)
DIST_FILES := \
	dist/avmesos_cli-$(PACKAGE_VERSION)-py3-none-any.whl \
	dist/avmesos_cli-$(PACKAGE_VERSION).tar.gz

help:
	    @echo "Makefile arguments:"
	    @echo ""
	    @echo "Makefile commands:"
	    @echo "build"
	    @echo "all"
			@echo "publish"
			@echo ${TAG}

.DEFAULT_GOAL := all

build:	
	@echo ">>>> Build python module"
	@$(PYTHON) setup.py sdist bdist_wheel

upload-check: build
	@$(TWINE) check $(DIST_FILES)

upload: upload-check
	@$(TWINE) upload --verbose --repository pypi $(DIST_FILES)

install:	
	@echo ">>>> Install python module"
	@pip3 install .

install-dev:	
	@echo ">>>> Install python module development"
	@pip install -e .

docs:
	@echo ">>>> Build docs"
	$(MAKE) -C $@

all: build
