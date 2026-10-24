#pragma once
#include "Message.h"
struct NotifyCampaignCheckpoint final : ServerMessage
{
    static constexpr auto Opcode = kNotifyCampaignCheckpoint;
    NotifyCampaignCheckpoint() : ServerMessage(Opcode) {}
    void SerializeRaw(TiltedPhoques::Buffer::Writer&) const noexcept override;
    void DeserializeRaw(TiltedPhoques::Buffer::Reader&) noexcept override;
    bool operator==(const NotifyCampaignCheckpoint& rhs) const noexcept { return RequestId == rhs.RequestId && Payload == rhs.Payload; }
    uint64_t RequestId{};
    String Payload; // Bounded JSON; upload bytes are base64-encoded, never logged.
};
