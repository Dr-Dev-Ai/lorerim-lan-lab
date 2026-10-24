#pragma once
#include "Message.h"
struct RequestCampaignCheckpoint final : ClientMessage
{
    static constexpr auto Opcode = kRequestCampaignCheckpoint;
    RequestCampaignCheckpoint() : ClientMessage(Opcode) {}
    void SerializeRaw(TiltedPhoques::Buffer::Writer&) const noexcept override;
    void DeserializeRaw(TiltedPhoques::Buffer::Reader&) noexcept override;
    bool operator==(const RequestCampaignCheckpoint& rhs) const noexcept { return RequestId == rhs.RequestId && Payload == rhs.Payload; }
    uint64_t RequestId{};
    String Payload; // Bounded JSON; upload bytes are base64-encoded, never logged.
};
