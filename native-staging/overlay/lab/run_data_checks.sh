#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
check_dir=$(mktemp -d)
trap 'rm -rf "$check_dir"' EXIT
c++ -std=c++20 -Wall -Wextra -Werror -I lab/native-support -I Code -I Code/common lab/calendar_data_test.cpp Code/common/DateTime.cpp -o "$check_dir/calendar"
"$check_dir/calendar"
c++ -std=c++20 -Wall -Wextra -Werror -I Code/common lab/dropped_claim_data_test.cpp -o "$check_dir/claims"
"$check_dir/claims"
c++ -std=c++20 -Wall -Wextra -Werror -Wno-reorder -ffunction-sections -fdata-sections -include lab/native-support/prelude.h -I lab/native-support -I Code/encoding lab/inventory_data_test.cpp Code/encoding/Structs/Inventory.cpp Code/encoding/Structs/GameId.cpp Code/encoding/Structs/MagicEquipment.cpp -Wl,--gc-sections -o "$check_dir/inventory"
"$check_dir/inventory"
python -m unittest discover -s lab -p 'test_*.py'
