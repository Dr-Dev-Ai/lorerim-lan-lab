#pragma once
struct DroppedItemPickupEvent
{
    uint32_t ActorId{};
    uint64_t DroppedId{};
    int32_t Count{};
};
