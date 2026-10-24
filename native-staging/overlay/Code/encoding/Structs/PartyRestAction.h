#pragma once
#include <cstdint>

enum class PartyRestAction : uint8_t
{
    Begin,
    Ready,
    Unsafe,
    Finish,
    Cancel,
    Complete
};
