#include <Messages/PartyRestRequest.h>
#include <TiltedCore/Serialization.hpp>

void PartyRestRequest::SerializeRaw(TiltedPhoques::Buffer::Writer& aWriter) const noexcept
{
    Serialization::WriteVarInt(aWriter, Session);
    Serialization::WriteFloat(aWriter, Hours);
    Serialization::WriteVarInt(aWriter, static_cast<uint8_t>(Action));
    Serialization::WriteBool(aWriter, AdvanceTime);
    Serialization::WriteVarInt(aWriter, Benefit);
}
void PartyRestRequest::DeserializeRaw(TiltedPhoques::Buffer::Reader& aReader) noexcept
{
    ClientMessage::DeserializeRaw(aReader);
    Session = Serialization::ReadVarInt(aReader);
    Hours = Serialization::ReadFloat(aReader);
    Action = static_cast<PartyRestAction>(Serialization::ReadVarInt(aReader));
    AdvanceTime = Serialization::ReadBool(aReader);
    Benefit = static_cast<uint8_t>(Serialization::ReadVarInt(aReader));
}
