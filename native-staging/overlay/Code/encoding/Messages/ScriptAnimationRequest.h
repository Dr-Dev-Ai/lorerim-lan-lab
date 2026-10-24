#pragma once

#include "Message.h"
#include "Structs/CachedString.h"
#include <Structs/GameId.h>

struct ScriptAnimationRequest final : ClientMessage
{
    static constexpr ClientOpcode Opcode = kScriptAnimationRequest;

    ScriptAnimationRequest()
        : ClientMessage(Opcode)
    {
    }

    void SerializeRaw(TiltedPhoques::Buffer::Writer& aWriter) const noexcept override;
    void DeserializeRaw(TiltedPhoques::Buffer::Reader& aReader) noexcept override;

    bool operator==(const ScriptAnimationRequest& acRhs) const noexcept { return Id == acRhs.Id && CellId == acRhs.CellId && Animation == acRhs.Animation && EventName == acRhs.EventName && GetOpcode() == acRhs.GetOpcode(); }

    GameId Id{};
    GameId CellId{};
    CachedString Animation;
    CachedString EventName;
};
