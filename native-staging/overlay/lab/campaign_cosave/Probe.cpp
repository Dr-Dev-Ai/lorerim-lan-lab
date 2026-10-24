// Pure SDK-serialization/ABI probe. Does not launch Skyrim or touch a profile.
#include <Windows.h>
#include <cstdint>
#include <cstring>
#include <vector>
#include <iostream>
using UInt32=uint32_t; using UInt64=uint64_t;
#include <PluginAPI.h>
#include <CampaignSave.h>
namespace
{
struct Chunk { uint32_t Type{},Version{}; std::vector<uint8_t> Bytes; };
std::vector<Chunk> s_chunks, s_written;
size_t s_next{},s_current{},s_offset{};
SKSESerializationInterface::EventCallback s_save{},s_load{},s_revert{};
SKSEMessagingInterface::EventCallback s_message{};
uint32_t s_uid{},s_barriers{};
CampaignSave::Read s_read{};
SKSESerializationInterface s_serialization{};
SKSEMessagingInterface s_messaging{};
bool Write(uint32_t type,uint32_t version,const void* bytes,uint32_t length)
{
    const auto* data=static_cast<const uint8_t*>(bytes);
    s_written.push_back({type,version,std::vector<uint8_t>(data,data+length)}); return true;
}
bool Next(uint32_t* type,uint32_t* version,uint32_t* length)
{
    if(s_next>=s_chunks.size())return false;
    s_current=s_next++;s_offset=0;
    *type=s_chunks[s_current].Type;*version=s_chunks[s_current].Version;*length=static_cast<uint32_t>(s_chunks[s_current].Bytes.size());return true;
}
uint32_t Read(void* buffer,uint32_t length)
{
    const auto& bytes=s_chunks[s_current].Bytes;
    if(length>bytes.size()-s_offset)length=static_cast<uint32_t>(bytes.size()-s_offset);
    std::memcpy(buffer,bytes.data()+s_offset,length);s_offset+=length;return length;
}
void Barrier()
{
    ++s_barriers;
    CampaignSave::Snapshot current;
    // A successful reentrant read proves the callback is not invoked under its lock.
    if(s_read && !s_read(&current,sizeof(current)))std::terminate();
}
void Message(uint32_t type,void* data=nullptr,uint32_t size=0)
{
    SKSEMessagingInterface::Message message{"SKSE",type,size,data};s_message(&message);
}
void Reload(const std::vector<Chunk>& chunks)
{
    char name[]="FixtureSave";
    Message(SKSEMessagingInterface::kMessage_PreLoadGame,name,sizeof(name)-1);
    s_revert(&s_serialization);
    s_chunks=chunks;s_next=s_offset=s_current=0;s_load(&s_serialization);
    Message(SKSEMessagingInterface::kMessage_PostLoadGame,reinterpret_cast<void*>(1),1);
}
}
#define CHECK(condition) do { if(!(condition)) { std::cerr<<"FAIL line "<<__LINE__<<"\n";return 1; } } while(0)
int main(int argc,char** argv)
{
    if(argc!=2)return 2;
    auto* module=LoadLibraryA(argv[1]);CHECK(module);
    auto pluginLoad=reinterpret_cast<bool (*)(const SKSEInterface*)>(GetProcAddress(module,"SKSEPlugin_Load"));
    auto* metadata=reinterpret_cast<SKSEPluginVersionData*>(GetProcAddress(module,"SKSEPlugin_Version"));
    s_read=reinterpret_cast<CampaignSave::Read>(GetProcAddress(module,"LoreRimCampaign_Read"));
    auto setHead=reinterpret_cast<CampaignSave::SetHead>(GetProcAddress(module,"LoreRimCampaign_SetHead"));
    auto registerBarrier=reinterpret_cast<CampaignSave::RegisterBarrier>(GetProcAddress(module,"LoreRimCampaign_RegisterBarrier"));
    CHECK(pluginLoad && metadata && metadata->dataVersion==1 && s_read && setHead && registerBarrier);
    CHECK(registerBarrier(Barrier));
    s_serialization.version=4;
    s_serialization.SetUniqueID=[](PluginHandle,uint32_t uid){s_uid=uid;};
    s_serialization.SetRevertCallback=[](PluginHandle,auto callback){s_revert=callback;};
    s_serialization.SetSaveCallback=[](PluginHandle,auto callback){s_save=callback;};
    s_serialization.SetLoadCallback=[](PluginHandle,auto callback){s_load=callback;};
    s_serialization.WriteRecord=Write;s_serialization.GetNextRecordInfo=Next;s_serialization.ReadRecordData=Read;
    s_messaging.interfaceVersion=2;
    s_messaging.RegisterListener=[](PluginHandle,const char*,auto callback){s_message=callback;return true;};
    SKSEInterface skse{};
    skse.QueryInterface=[](uint32_t type)->void* {return type==kInterface_Serialization?static_cast<void*>(&s_serialization):type==kInterface_Messaging?static_cast<void*>(&s_messaging):nullptr;};
    skse.GetPluginHandle=[]()->PluginHandle{return 1;};
    CHECK(pluginLoad(&skse));CHECK(s_uid==CampaignSave::PluginId && s_save && s_load && s_revert && s_message);
    CampaignSave::Identity identity;
    std::strcpy(identity.Character,"11111111-1111-4111-8111-111111111111");
    std::strcpy(identity.Campaign,"22222222-2222-4222-8222-222222222222");
    std::strcpy(identity.Epoch,"33333333-3333-4333-8333-333333333333");
    const auto* bytes=reinterpret_cast<const uint8_t*>(&identity);
    Chunk record{CampaignSave::IdentityRecord,1,std::vector<uint8_t>(bytes,bytes+sizeof(identity))};
    Reload({record});
    CampaignSave::Snapshot snapshot;CHECK(s_read(&snapshot,sizeof(snapshot)));
    CHECK(snapshot.Status==CampaignSave::Ready && std::strcmp(snapshot.SaveName,"FixtureSave")==0 && s_barriers==2);
    CHECK(std::memcmp(&snapshot.Record,&identity,sizeof(identity))==0);
    CHECK(!setHead(snapshot.Generation+1,identity.Epoch,"",0));
    CHECK(!setHead(snapshot.Generation,identity.Campaign,"",0));
    CHECK(setHead(snapshot.Generation,identity.Epoch,"44444444-4444-4444-8444-444444444444",99));
    CHECK(setHead(snapshot.Generation,identity.Epoch,"",100));
    s_save(&s_serialization);CHECK(s_written.size()==1 && s_written[0].Bytes.size()==160);
    const auto saved=s_written;
    Reload(saved);CHECK(s_read(&snapshot,sizeof(snapshot)) && snapshot.Status==CampaignSave::Ready && snapshot.Record.Revision==100);
    Reload({record,record});CHECK(s_read(&snapshot,sizeof(snapshot)) && snapshot.Status==CampaignSave::Invalid);
    auto malformed=record;malformed.Bytes.pop_back();Reload({malformed});CHECK(s_read(&snapshot,sizeof(snapshot)) && snapshot.Status==CampaignSave::Invalid);
    Reload({});CHECK(s_read(&snapshot,sizeof(snapshot)) && snapshot.Status==CampaignSave::NeedsSave && std::strlen(snapshot.Record.Character)==36);
    CHECK(!setHead(snapshot.Generation,identity.Epoch,"",0));
    Message(SKSEMessagingInterface::kMessage_PreLoadGame);CHECK(s_read(&snapshot,sizeof(snapshot)) && snapshot.Status==CampaignSave::Loading);
    CHECK(!s_read(&snapshot,sizeof(snapshot)-1));
    CHECK(registerBarrier(nullptr));
    std::cout<<"PASS: companion ABI, serialization roundtrip, preload invalidation, epoch checks, duplicate/truncated record rejection, legacy migration\n";
    // Keep module loaded until process exit; callbacks point into it.
    return 0;
}
