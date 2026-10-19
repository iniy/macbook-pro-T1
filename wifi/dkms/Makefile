# SPDX-License-Identifier: MIT
KVERSION ?= $(shell uname -r)
CC = x86_64-linux-gnu-gcc

.PHONY: all prepare clean
all: prepare
	$(MAKE) -C /lib/modules/$(KVERSION)/build M=$(CURDIR)/build CC=$(CC) W=1 modules
prepare:
	python3 prepare.py $(KVERSION)
clean:
	python3 -c 'from pathlib import Path; import shutil; p=Path("build"); p.is_dir() and not p.is_symlink() and shutil.rmtree(p)'
