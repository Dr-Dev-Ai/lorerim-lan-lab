#include <Messages/NotifyCampaignCheckpoint.h>
#include <TiltedCore/Serialization.hpp>
void NotifyCampaignCheckpoint::SerializeRaw(TiltedPhoques::Buffer::Writer& writer) const noexcept
{
    Serialization::WriteVarInt(writer, RequestId); Serialization::WriteString(writer, Payload);
}
void NotifyCampaignCheckpoint::DeserializeRaw(TiltedPhoques::Buffer::Reader& reader) noexcept
{
    ServerMessage::DeserializeRaw(reader);
    RequestId = Serialization::ReadVarInt(reader); Payload = Serialization::ReadString(reader);
}
