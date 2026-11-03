#!/bin/sh
# Dentro del cliente ya configurado (local o bastión AWS). No detiene VMs.
set -eu
python -m tests.regression
python -m tests.test_statistics
echo 'Contrato y estadística: OK. Para fallos locales use scripts/verify_local.py.'
echo 'Las caídas de VMs y benchmark AWS se ejecutan y documentan por separado.'
