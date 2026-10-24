#include <Messages/NotifyCampaignAction.h>
#include <TiltedCore/Serialization.hpp>
void NotifyCampaignAction::SerializeRaw(TiltedPhoques::Buffer::Writer& w) const noexcept
{
    Serialization::WriteVarInt(w, RequestId);
    Actor.Serialize(w);
    Serialization::WriteVarInt(w, static_cast<uint8_t>(Action));
    Serialization::WriteBool(w, Enabled);
    Serialization::WriteBool(w, Allowed);
    Serialization::WriteBool(w, IsLeader);
    Serialization::WriteString(w, Epoch);
    Serialization::WriteString(w, Checkpoint);
    Serialization::WriteVarInt(w, Revision);
}
void NotifyCampaignAction::DeserializeRaw(TiltedPhoques::Buffer::Reader& reader) noexcept
{
    ServerMessage::DeserializeRaw(reader);
    RequestId = Serialization::ReadVarInt(reader);
    Actor.Deserialize(reader);
    Action = static_cast<CampaignAction>(Serialization::ReadVarInt(reader));
    Enabled = Serialization::ReadBool(reader);
    Allowed = Serialization::ReadBool(reader);
    IsLeader = Serialization::ReadBool(reader);
    Epoch = Serialization::ReadString(reader);
    Checkpoint = Serialization::ReadString(reader);
    Revision = Serialization::ReadVarInt(reader);
}
