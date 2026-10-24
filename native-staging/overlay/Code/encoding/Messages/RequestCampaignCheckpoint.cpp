#include <Messages/RequestCampaignCheckpoint.h>
#include <TiltedCore/Serialization.hpp>
void RequestCampaignCheckpoint::SerializeRaw(TiltedPhoques::Buffer::Writer& writer) const noexcept
{
    Serialization::WriteVarInt(writer, RequestId); Serialization::WriteString(writer, Payload);
}
void RequestCampaignCheckpoint::DeserializeRaw(TiltedPhoques::Buffer::Reader& reader) noexcept
{
    ClientMessage::DeserializeRaw(reader);
    RequestId = Serialization::ReadVarInt(reader); Payload = Serialization::ReadString(reader);
}
