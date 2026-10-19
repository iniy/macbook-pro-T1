# SPDX-License-Identifier: MIT
KVERSION ?= $(shell uname -r)
CC = x86_64-linux-gnu-gcc
FLAGS = -DINTERNAL_MIKE_ONLY -DAPPLE_PINSENSE_FIXUP -DAPPLE_CODECS -DCONFIG_SND_HDA_RECONFIG=1
FLAGS += -Wno-unused-variable -Wno-unused-function

.PHONY: all prepare clean
all: prepare
	$(MAKE) -C /lib/modules/$(KVERSION)/build M=$(CURDIR)/build CC=$(CC) CFLAGS_MODULE="$(FLAGS)" modules
prepare:
	python3 prepare.py $(KVERSION)
clean:
	rm -rf build
