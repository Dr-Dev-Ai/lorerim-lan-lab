#include <Messages/NotifyInventoryChanges.h>
#include <TiltedCore/Serialization.hpp>

void NotifyInventoryChanges::SerializeRaw(TiltedPhoques::Buffer::Writer& aWriter) const noexcept
{
    Serialization::WriteVarInt(aWriter, DroppedId);
    Serialization::WriteVarInt(aWriter, ClaimId);
    Serialization::WriteVarInt(aWriter, ServerId);
    Serialization::WriteVarInt(aWriter, OwnershipEpoch);
    Item.Serialize(aWriter);
    Serialization::WriteBool(aWriter, Drop);
}

void NotifyInventoryChanges::DeserializeRaw(TiltedPhoques::Buffer::Reader& aReader) noexcept
{
    ServerMessage::DeserializeRaw(aReader);

    DroppedId = Serialization::ReadVarInt(aReader);
    ClaimId = Serialization::ReadVarInt(aReader);
    ServerId = Serialization::ReadVarInt(aReader) & 0xFFFFFFFF;
    OwnershipEpoch = Serialization::ReadVarInt(aReader) & 0xFFFFFFFF;
    Item.Deserialize(aReader);
    Drop = Serialization::ReadBool(aReader);
}
