#!/bin/bash
cd "$(dirname "$0")"

chmod +x ./ЗАПУСТИТЬ_ДЕЖУРКУ.sh ./СОЗДАТЬ_ЯРЛЫК.sh 2>/dev/null || true

bash ./СОЗДАТЬ_ЯРЛЫК.sh
bash ./ЗАПУСТИТЬ_ДЕЖУРКУ.sh
