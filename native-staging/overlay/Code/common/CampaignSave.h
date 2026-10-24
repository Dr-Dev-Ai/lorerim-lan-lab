#pragma once
#include <cstdint>
// Stable C ABI shared with the SKSE companion. No game structures/offsets.
namespace CampaignSave
{
inline constexpr uint32_t PluginId = 0x4c524350;
inline constexpr uint32_t IdentityRecord = 0x4c524944;
inline constexpr uint32_t Schema = 1;
enum State : uint32_t { Loading, Ready, NeedsSave, Invalid };
#pragma pack(push, 1)
struct Identity
{
    uint32_t Version{Schema};
    char Character[37]{};
    char Campaign[37]{};
    char Epoch[37]{};
    char Checkpoint[37]{};
    uint64_t Revision{};
};
#pragma pack(pop)
static_assert(sizeof(Identity) == 160);
struct Snapshot
{
    uint32_t Size{sizeof(Snapshot)};
    uint32_t Status{Loading};
    uint64_t Generation{};
    Identity Record;
    char SaveName[1024]{};
};
using Read = bool (*)(Snapshot*, uint32_t);
using Barrier = void (*)();
using RegisterBarrier = bool (*)(Barrier);
using SetHead = bool (*)(uint64_t, const char*, const char*, uint64_t);
}
