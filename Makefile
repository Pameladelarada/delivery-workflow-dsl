# Makefile - Delivery Workflow DSL
#
#   make          compila el compilador del DSL
#   make test     compila y ejecuta todas las pruebas
#   make web      levanta la aplicacion Flask en http://127.0.0.1:5000
#   make venv     crea el entorno virtual e instala las dependencias
#   make clean    borra los artefactos de compilacion
#
# Funciona en Linux, macOS, WSL y Git Bash / MSYS2 en Windows.
# En PowerShell puro, build.ps1 sigue disponible.

CXX      ?= g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -Wpedantic
BIN      := bin/delivery_compiler
PY       := .venv/bin/python

ifeq ($(OS),Windows_NT)
    BIN := $(BIN).exe
    PY  := .venv/Scripts/python.exe
endif

.PHONY: all test web venv clean

all: $(BIN)

bin:
	@mkdir -p bin

$(BIN): compiler/main.cpp | bin
	@echo "Compilando el compilador del DSL..."
	@$(CXX) $(CXXFLAGS) -o $@ $<
	@echo "Listo: $@"

venv: $(PY)

$(PY):
	@echo "Creando el entorno virtual..."
	@python3 -m venv .venv
	@$(PY) -m pip install --quiet --upgrade pip
	@$(PY) -m pip install --quiet -r requirements.txt pytest
	@echo "Listo."

test: $(BIN) $(PY)
	@$(PY) -m pytest tests/ -q

web: $(BIN) $(PY)
	@$(PY) web/app.py

clean:
	@rm -rf bin .pytest_cache tests/__pycache__ web/__pycache__
	@echo "Artefactos eliminados."
