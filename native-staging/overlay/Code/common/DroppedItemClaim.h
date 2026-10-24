#pragma once
#include <cstdint>

// The server dispatcher serializes calls; quantity is committed only on success.
inline bool ConsumeDroppedCount(int32_t& aRemaining, int32_t aRequested) noexcept
{
    if (aRequested <= 0 || aRemaining <= 0 || aRequested > aRemaining)
        return false;
    aRemaining -= aRequested;
    return true;
}
