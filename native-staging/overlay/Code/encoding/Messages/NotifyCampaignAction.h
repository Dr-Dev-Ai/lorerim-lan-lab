#pragma once
#include "Message.h"
#include <Structs/GameId.h>
#include <Structs/CampaignAction.h>
struct NotifyCampaignAction final : ServerMessage
{
    static constexpr ServerOpcode Opcode = kNotifyCampaignAction;
    NotifyCampaignAction() : ServerMessage(Opcode) {}
    void SerializeRaw(TiltedPhoques::Buffer::Writer&) const noexcept override;
    void DeserializeRaw(TiltedPhoques::Buffer::Reader&) noexcept override;
    bool operator==(const NotifyCampaignAction& rhs) const noexcept { return RequestId == rhs.RequestId && Actor == rhs.Actor && Action == rhs.Action && Enabled == rhs.Enabled && Allowed == rhs.Allowed && IsLeader == rhs.IsLeader && Epoch == rhs.Epoch && Checkpoint == rhs.Checkpoint && Revision == rhs.Revision; }
    uint64_t RequestId{};
    GameId Actor{};
    CampaignAction Action{CampaignAction::Join};
    bool Enabled{};
    bool Allowed{};
    bool IsLeader{};
    String Epoch, Checkpoint;
    uint64_t Revision{};
};
