#include <Messages/CampaignActionRequest.h>
#include <TiltedCore/Serialization.hpp>
void CampaignActionRequest::SerializeRaw(TiltedPhoques::Buffer::Writer& w) const noexcept
{
    Serialization::WriteVarInt(w, RequestId);
    Actor.Serialize(w);
    Serialization::WriteVarInt(w, static_cast<uint8_t>(Action));
    Serialization::WriteString(w, Credential);
    Serialization::WriteString(w, SaveProof);
}
void CampaignActionRequest::DeserializeRaw(TiltedPhoques::Buffer::Reader& reader) noexcept
{
    ClientMessage::DeserializeRaw(reader);
    RequestId = Serialization::ReadVarInt(reader);
    Actor.Deserialize(reader);
    Action = static_cast<CampaignAction>(Serialization::ReadVarInt(reader));
    Credential = Serialization::ReadString(reader);
    SaveProof = Serialization::ReadString(reader);
}
