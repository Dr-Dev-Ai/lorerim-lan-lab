#include <Structs/Inventory.h>
#include <cassert>
#include <iostream>

int main()
{
    Inventory::Entry sword;
    sword.BaseId = GameId{1, 100};
    sword.Count = 1;
    sword.ExtraHealth = 1.25f;
    sword.ExtraEnchantId = GameId{0xffffffff, 1};
    sword.EnchantData.IsWeapon = true;
    sword.EnchantData.Effects.push_back({10.f, 0, 2, 12.f, GameId{2, 200}});
    Inventory::Entry other = sword;
    assert(sword.CanBeMerged(other));
    other.EnchantData.Effects[0].Magnitude = 20.f;
    assert(!sword.CanBeMerged(other));
    other = sword;
    other.EnchantData.Effects[0].Duration++;
    assert(!sword.CanBeMerged(other));
    other = sword;
    other.EnchantData.IsWeapon = false;
    assert(!sword.CanBeMerged(other));
    other = sword;
    other.ExtraCharge = 5.f;
    assert(!sword.CanBeMerged(other));
    Inventory inventory;
    inventory.AddOrRemoveEntry(sword);
    inventory.AddOrRemoveEntry(other);
    assert(inventory.Entries.size() == 2);
    Inventory equipped;
    other.ExtraWorn = true;
    equipped.Entries.push_back(other);
    inventory.UpdateEquipment(equipped);
    assert(!inventory.Entries[0].IsWorn());
    assert(inventory.Entries[1].ExtraWorn);
    Inventory copy = inventory;
    copy.CurrentMagicEquipment.RightHandSpell = GameId{3, 300};
    assert(copy != inventory);
    Inventory empty;
    other.Count = -1;
    empty.AddOrRemoveEntry(other);
    assert(empty.Entries.empty());
    std::cout << "PASS: enchantment variants, worn instance selection, magic equipment equality, and unknown removal\n";
}
