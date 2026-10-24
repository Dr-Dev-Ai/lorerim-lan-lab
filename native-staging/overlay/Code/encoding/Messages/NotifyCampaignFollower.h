#pragma once
#include "Message.h"
#include <Structs/GameId.h>
// Delivered only to the current AI simulator, tied to its ownership epoch.
struct NotifyCampaignFollower final : ServerMessage
{
    static constexpr ServerOpcode Opcode = kNotifyCampaignFollower;
    NotifyCampaignFollower() : ServerMessage(Opcode) {}
    void SerializeRaw(TiltedPhoques::Buffer::Writer&) const noexcept override;
    void DeserializeRaw(TiltedPhoques::Buffer::Reader&) noexcept override;
    bool operator==(const NotifyCampaignFollower& rhs) const noexcept { return Actor == rhs.Actor && OwnershipEpoch == rhs.OwnershipEpoch && Sequence == rhs.Sequence && Policy == rhs.Policy; }
    GameId Actor;
    uint32_t OwnershipEpoch{};
    uint64_t Sequence{};
    uint8_t Policy{}; // 1 park, 2 follow, 3 wait; never resurrect or recreate.
};
