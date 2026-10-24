// SDK interfaces verified against ianpatt/skse64, PluginAPI.h and
// Serialization.cpp. The downloaded SDK is a build dependency, not vendored.
#include <Windows.h>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <charconv>
#include <mutex>
#include <atomic>
using UInt32 = uint32_t;
using UInt64 = uint64_t;
#include <PluginAPI.h>
#include <CampaignSave.h>

namespace
{
std::mutex s_mutex;
CampaignSave::Snapshot s_snapshot;
CampaignSave::Barrier s_barrier{};
bool s_loadedRecord{}, s_invalidRecord{};

bool Uuid(const char* value, bool empty = false)
{
    if (empty && value[0] == 0) return true;
    for (size_t i = 0; i < 36; ++i)
    {
        const char ch = value[i];
        if (i == 8 || i == 13 || i == 18 || i == 23) { if (ch != '-') return false; }
        else if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f'))) return false;
    }
    return value[36] == 0;
}
bool Valid(const CampaignSave::Identity& record)
{
    return record.Version == CampaignSave::Schema && Uuid(record.Character)
        && Uuid(record.Campaign, true) && Uuid(record.Epoch, true) && Uuid(record.Checkpoint, true);
}
void Generate()
{
    GUID guid{};
    if (FAILED(CoCreateGuid(&guid))) { s_snapshot.Status = CampaignSave::Invalid; return; }
    auto& record = s_snapshot.Record;
    record = {};
    std::snprintf(record.Character, sizeof(record.Character),
        "%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x", guid.Data1, guid.Data2, guid.Data3,
        guid.Data4[0], guid.Data4[1], guid.Data4[2], guid.Data4[3], guid.Data4[4], guid.Data4[5], guid.Data4[6], guid.Data4[7]);
    // Initial enrollment is configured explicitly by the campaign manager.
    constexpr auto ini = ".\\Data\\SKSE\\Plugins\\LoreRimCampaign.ini";
    GetPrivateProfileStringA("Campaign", "Id", "", record.Campaign, sizeof(record.Campaign), ini);
    GetPrivateProfileStringA("Campaign", "Epoch", "", record.Epoch, sizeof(record.Epoch), ini);
    GetPrivateProfileStringA("Campaign", "Checkpoint", "", record.Checkpoint, sizeof(record.Checkpoint), ini);
    char revision[32]{};
    GetPrivateProfileStringA("Campaign", "Revision", "0", revision, sizeof(revision), ini);
    const auto parsed = std::from_chars(revision, revision + std::strlen(revision), record.Revision);
    if (parsed.ec != std::errc{} || *parsed.ptr != 0) { s_snapshot.Status = CampaignSave::Invalid; return; }
    s_snapshot.Status = Valid(record) ? CampaignSave::NeedsSave : CampaignSave::Invalid;
}
void Invalidate(bool clearName)
{
    CampaignSave::Barrier callback;
    {
        std::lock_guard lock(s_mutex);
        ++s_snapshot.Generation;
        s_snapshot.Record = {}; s_snapshot.Status = CampaignSave::Loading;
        if (clearName) s_snapshot.SaveName[0] = 0;
        s_loadedRecord = s_invalidRecord = false;
        callback = s_barrier;
    }
    // Never hold the companion lock while calling into the client.
    if (callback) callback();
}
void Save(SKSESerializationInterface* api)
{
    std::lock_guard lock(s_mutex);
    if (s_snapshot.Status == CampaignSave::Invalid || !Valid(s_snapshot.Record)) return;
    if (!api->WriteRecord(CampaignSave::IdentityRecord, CampaignSave::Schema, &s_snapshot.Record, sizeof(s_snapshot.Record)))
        s_snapshot.Status = CampaignSave::Invalid;
    // A write callback is not proof the .ess/.skse pair finished. Require reload.
}
void Load(SKSESerializationInterface* api)
{
    std::lock_guard lock(s_mutex);
    uint32_t type{}, version{}, length{};
    while (api->GetNextRecordInfo(&type, &version, &length))
    {
        if (type != CampaignSave::IdentityRecord) continue;
        CampaignSave::Identity record;
        if (s_loadedRecord || s_invalidRecord || version != CampaignSave::Schema || length != sizeof(record)
            || api->ReadRecordData(&record, sizeof(record)) != sizeof(record) || !Valid(record))
        { s_invalidRecord = true; continue; }
        s_snapshot.Record = record; s_loadedRecord = true;
    }
    if (s_invalidRecord) s_snapshot.Status = CampaignSave::Invalid;
    else if (!s_loadedRecord) Generate();
}
void Revert(SKSESerializationInterface*) { Invalidate(false); }
void Message(SKSEMessagingInterface::Message* message)
{
    if (!message) return;
    switch (message->type)
    {
    case SKSEMessagingInterface::kMessage_PreLoadGame:
        Invalidate(true);
        if (message->data && message->dataLen && message->dataLen < sizeof(s_snapshot.SaveName))
        {
            std::lock_guard lock(s_mutex);
            std::memcpy(s_snapshot.SaveName, message->data, message->dataLen);
            s_snapshot.SaveName[message->dataLen] = 0;
        }
        break;
    case SKSEMessagingInterface::kMessage_PostLoadGame:
        {
            std::lock_guard lock(s_mutex);
            // SDK dispatches the success boolean encoded in the data pointer.
            if (!message->data || s_invalidRecord) s_snapshot.Status = CampaignSave::Invalid;
            else if (s_loadedRecord) s_snapshot.Status = CampaignSave::Ready;
        }
        break;
    case SKSEMessagingInterface::kMessage_NewGame:
        Invalidate(true);
        { std::lock_guard lock(s_mutex); Generate(); }
        break;
    default: break;
    }
}
}
extern "C" __declspec(dllexport) bool LoreRimCampaign_Read(CampaignSave::Snapshot* out, uint32_t bytes)
{
    if (!out || bytes != sizeof(*out)) return false;
    std::lock_guard lock(s_mutex); *out = s_snapshot; return true;
}
extern "C" __declspec(dllexport) bool LoreRimCampaign_RegisterBarrier(CampaignSave::Barrier callback)
{
    std::lock_guard lock(s_mutex); s_barrier = callback; return true;
}
extern "C" __declspec(dllexport) bool LoreRimCampaign_SetHead(uint64_t generation, const char* epoch, const char* checkpoint, uint64_t revision)
{
    if (!epoch || !checkpoint || !Uuid(epoch) || !Uuid(checkpoint, true)) return false;
    std::lock_guard lock(s_mutex);
    if (s_snapshot.Status != CampaignSave::Ready || s_snapshot.Generation != generation
        || std::strcmp(s_snapshot.Record.Epoch, epoch) != 0) return false;
    std::strncpy(s_snapshot.Record.Checkpoint, checkpoint, 36);
    s_snapshot.Record.Checkpoint[36] = 0;
    s_snapshot.Record.Revision = revision;
    return true;
}
extern "C"
{
__declspec(dllexport) SKSEPluginVersionData SKSEPlugin_Version = {
    SKSEPluginVersionData::kVersion, 4, "LoreRimCampaignCosave", "Codex", "",
    SKSEPluginVersionData::kVersionIndependentEx_NoStructUse, 0,
    {(1u << 24) | (6u << 16) | (1170u << 4), (1u << 24) | (7u << 16) | (104u << 4), 0}, 0};
__declspec(dllexport) bool SKSEPlugin_Load(const SKSEInterface* skse)
{
    if (!skse || skse->isEditor) return false;
    auto* serialization = static_cast<SKSESerializationInterface*>(skse->QueryInterface(kInterface_Serialization));
    auto* messaging = static_cast<SKSEMessagingInterface*>(skse->QueryInterface(kInterface_Messaging));
    if (!serialization || serialization->version < 4 || !messaging || messaging->interfaceVersion < 2) return false;
    const auto handle = skse->GetPluginHandle();
    if (handle == kPluginHandle_Invalid) return false;
    serialization->SetUniqueID(handle, CampaignSave::PluginId);
    serialization->SetRevertCallback(handle, Revert);
    serialization->SetSaveCallback(handle, Save);
    serialization->SetLoadCallback(handle, Load);
    return messaging->RegisterListener(handle, "SKSE", Message);
}
}
