#include <DroppedItemClaim.h>
#include <cassert>
#include <climits>
#include <iostream>
int main()
{
    int32_t remaining = 5;
    assert(ConsumeDroppedCount(remaining, 5));
    assert(!ConsumeDroppedCount(remaining, 5)); // competing full-stack pickup
    assert(remaining == 0);
    remaining = 5;
    assert(ConsumeDroppedCount(remaining, 3));
    assert(remaining == 2);
    assert(!ConsumeDroppedCount(remaining, 3));
    assert(remaining == 2);
    assert(ConsumeDroppedCount(remaining, 2));
    for (int32_t invalid : {0, -1, INT_MIN, INT_MAX})
    {
        remaining = 4;
        assert(!ConsumeDroppedCount(remaining, invalid));
        assert(remaining == 4);
    }
    remaining = INT_MAX;
    assert(ConsumeDroppedCount(remaining, INT_MAX));
    assert(remaining == 0);
    std::cout << "PASS: competing claims, partial stacks, invalid counts, and integer limits\n";
}
