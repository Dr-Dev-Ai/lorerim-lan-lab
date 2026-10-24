#include <Messages/NotifyCampaignFollower.h>
#include <TiltedCore/Serialization.hpp>
void NotifyCampaignFollower::SerializeRaw(TiltedPhoques::Buffer::Writer& writer) const noexcept
{
    Actor.Serialize(writer);
    Serialization::WriteVarInt(writer, OwnershipEpoch);
    Serialization::WriteVarInt(writer, Sequence);
    Serialization::WriteVarInt(writer, Policy);
}
void NotifyCampaignFollower::DeserializeRaw(TiltedPhoques::Buffer::Reader& reader) noexcept
{
    ServerMessage::DeserializeRaw(reader);
    Actor.Deserialize(reader);
    OwnershipEpoch = static_cast<uint32_t>(Serialization::ReadVarInt(reader));
    Sequence = Serialization::ReadVarInt(reader);
    Policy = static_cast<uint8_t>(Serialization::ReadVarInt(reader));
}
