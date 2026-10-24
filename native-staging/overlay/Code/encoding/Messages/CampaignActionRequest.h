#pragma once
#include "Message.h"
#include <Structs/GameId.h>
#include <Structs/CampaignAction.h>
struct CampaignActionRequest final : ClientMessage
{
    static constexpr ClientOpcode Opcode = kCampaignActionRequest;
    CampaignActionRequest() : ClientMessage(Opcode) {}
    void SerializeRaw(TiltedPhoques::Buffer::Writer&) const noexcept override;
    void DeserializeRaw(TiltedPhoques::Buffer::Reader&) noexcept override;
    bool operator==(const CampaignActionRequest& rhs) const noexcept { return RequestId == rhs.RequestId && Actor == rhs.Actor && Action == rhs.Action && Credential == rhs.Credential && SaveProof == rhs.SaveProof; }
    uint64_t RequestId{};
    GameId Actor{};
    CampaignAction Action{CampaignAction::Join};
    String SaveProof;
    String Credential; // Sent only during campaign attach; never log this payload.
};
