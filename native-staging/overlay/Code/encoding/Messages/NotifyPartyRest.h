#pragma once
#include "Message.h"
#include <Structs/PartyRestAction.h>

struct NotifyPartyRest final : ServerMessage
{
    static constexpr ServerOpcode Opcode = kNotifyPartyRest;
    NotifyPartyRest() : ServerMessage(Opcode) {}
    void SerializeRaw(TiltedPhoques::Buffer::Writer& aWriter) const noexcept override;
    void DeserializeRaw(TiltedPhoques::Buffer::Reader& aReader) noexcept override;
    bool operator==(const NotifyPartyRest& acRhs) const noexcept
    {
        return Benefit == acRhs.Benefit && Session == acRhs.Session && Hours == acRhs.Hours && Action == acRhs.Action && AdvanceTime == acRhs.AdvanceTime;
    }
    uint8_t Benefit{}; // 0 none, 1 rested, 2 well rested, 3 lover comfort
    uint64_t Session{};
    float Hours{};
    PartyRestAction Action{PartyRestAction::Cancel};
    bool AdvanceTime{false};
};
