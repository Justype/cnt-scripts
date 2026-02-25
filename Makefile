# Build container outputs under build/ from defs under build-scripts.
# apptainer makes SIFs; condatainer creates prefixes.
# run `make` or `make sif` to build base_image SIFs (default)
# run `make all` to build SIFs + all other defs as prefix dirs
# run `make ubuntu20` to build only ubuntu20 targets, etc.
# run `make clean` to wipe build/
CONDATINER ?= condatainer
COND_CREATE ?= create -p
APPTAINER ?= apptainer
APPT_BUILD ?= build
COND_FLAGS ?=
APPT_FLAGS ?=

# arch suffix added to outputs
ARCH := $(shell uname -m)
SUFFIX := _$(ARCH)

# Locate .def files in build-scripts/ubuntu* (skip numeric R releases
# and code-server.def).  Strip the leading build-scripts/.
DEF_SRCS := $(shell find build-scripts/ubuntu* -type f -name '*.def' \
	-not -name 'r[0-9]*.def' \
	-not -name 'code-server.def' | sed 's|^build-scripts/||')

# make a SIF for each base_image.def
BASE_DEFS := $(filter %base_image.def,$(DEF_SRCS))
SIF_TARGETS := $(patsubst %.def,build/%$(SUFFIX).sif,$(BASE_DEFS))

# all other definitions become prefix targets
SQF_TARGETS := $(patsubst %.def,build/%$(SUFFIX),$(filter-out %base_image.def,$(DEF_SRCS)))

# Aggregate non-sif targets
OTHER_TARGETS := $(SQF_TARGETS)

# sif target: build only the SIFs
.PHONY: sif
sif: $(SIF_TARGETS)
	@echo "Built SIF targets: $(SIF_TARGETS)"

.PHONY: all help list clean
all: $(SIF_TARGETS) $(SQF_TARGETS)
	@echo "Built all targets: $(SIF_TARGETS) $(SQF_TARGETS)"

help: ## Show help
	@echo "Usage: make [target]"
	@echo "Targets:"
	@echo "  sif (default) - build base_image SIFs via apptainer"
	@echo "  all - build SIFs + all other defs as prefix dirs via condatainer"
	@echo "  clean - remove build/ directory"
	@echo "  ubuntu20, ubuntu22, ubuntu24 - build only the artifacts for that release"
	@echo "Variables you can override: APPTAINER, CONDATINER, APPT_FLAGS, COND_FLAGS"

# build a base_image SIF from corresponding build-scripts file
build/%$(SUFFIX).sif: build-scripts/%.def
	@echo "[apptainer] Building $@ from $<"
	@mkdir -p $(dir $@)
	$(APPTAINER) $(APPT_BUILD) $@ $(APPT_FLAGS) $<

# create prefix dirs via condatainer; computes def path from target
build/%$(SUFFIX):
	@def_path="build-scripts/$$(echo "$@" | sed 's|^build/||; s|$(SUFFIX)$$||').def"; \
	if [ ! -e "$$def_path" ]; then echo "ERROR: def file not found: $$def_path"; exit 1; fi; \
	echo "[condatainer] Creating $@ from $$def_path"; \
	mkdir -p $(dir $@); \
	$(CONDATINER) $(COND_CREATE) $@ -f "$$def_path" $(COND_FLAGS); \
	touch $@.sqf


# listing helpers
list: ## List the discovered .def files and planned targets
	@echo "all"
	@printf '%s\n' $(SIF_TARGETS) $(SQF_TARGETS)
	@echo
	@for v in $(UBUNTU_VERS); do \
		echo "$$v"; \
		printf '%s\n' $(SIF_TARGETS) $(SQF_TARGETS) | grep "^build/$$v/" || true; \
		echo; \
	done
	@echo "sif"
	@printf '%s\n' $(SIF_TARGETS)

# ubuntu-only listing helper
.PHONY: list-ubuntu
list-ubuntu: ## Show only ubuntu-related build paths
	@printf '%s\n' $(SIF_TARGETS) $(SQF_TARGETS) | grep '^build/ubuntu' || true

clean: ## Remove build artifacts
	rm -rf build/
	@echo "cleaned build/"

# per-release build targets (ubuntuXX) derived from directories
UBUNTU_VERS := $(shell find build-scripts/ubuntu* -maxdepth 0 -type d -printf '%f\n' 2>/dev/null | sort)
.PHONY: $(UBUNTU_VERS)
# each rule depends on all outputs underneath build/<release>/
$(foreach v,$(UBUNTU_VERS),$(eval $(v): $(filter build/$(v)/%,$(SIF_TARGETS) $(SQF_TARGETS))))

# Avoid errors if no SIF targets are present
.SECONDARY:

# end of Makefile
