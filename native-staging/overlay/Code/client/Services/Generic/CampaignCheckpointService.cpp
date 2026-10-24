#include <Services/CampaignCheckpointService.h>
#include <Services/CampaignService.h>
#include <Services/PapyrusService.h>
#include <World.h>
#include <Events/UpdateEvent.h>
#include <Events/DisconnectedEvent.h>
#include <Messages/RequestCampaignCheckpoint.h>
#include <Messages/NotifyCampaignCheckpoint.h>
#include <Games/Skyrim/Interface/UI.h>
#include <PlayerCharacter.h>
#include <nlohmann/json.hpp>
#include <cryptopp/sha.h>
#include <fstream>
#include <chrono>
namespace
{
using Json=nlohmann::json;
uint64_t Now(){return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
std::string Hash(const std::filesystem::path& path)
{
    std::ifstream file(path,std::ios::binary);if(!file)return {};
    CryptoPP::SHA256 sha;char bytes[65536];while(file){file.read(bytes,sizeof(bytes));if(file.gcount()>0)sha.Update(reinterpret_cast<CryptoPP::byte*>(bytes),static_cast<size_t>(file.gcount()));}
    if(!file.eof())return {};
    CryptoPP::byte digest[32];sha.Final(digest);std::string result(64,'0');constexpr char hex[]="0123456789abcdef";
    for(size_t i=0;i<32;++i){result[2*i]=hex[digest[i]>>4];result[2*i+1]=hex[digest[i]&15];}return result;
}
std::string Base64(const char* bytes,size_t count)
{
    constexpr char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string result;result.reserve((count+2)/3*4);
    for(size_t i=0;i<count;i+=3)
    {
        const uint32_t value=(static_cast<uint32_t>(static_cast<uint8_t>(bytes[i]))<<16)
            |(i+1<count?static_cast<uint32_t>(static_cast<uint8_t>(bytes[i+1]))<<8:0)
            |(i+2<count?static_cast<uint8_t>(bytes[i+2]):0);
        result.push_back(alphabet[value>>18]);result.push_back(alphabet[value>>12&63]);
        result.push_back(i+1<count?alphabet[value>>6&63]:'=');result.push_back(i+2<count?alphabet[value&63]:'=');
    }
    return result;
}
}
CampaignCheckpointService::CampaignCheckpointService(World& world,entt::dispatcher& dispatcher,TransportService& transport):m_world(world),m_transport(transport)
{
    wchar_t value[2048]{};
    GetPrivateProfileStringW(L"Campaign",L"SaveDirectory",L"",value,2048,L".\\Data\\SKSE\\Plugins\\LoreRimCampaign.ini");m_saves=value;
    GetPrivateProfileStringW(L"Campaign",L"ProfileDirectory",L"",value,2048,L".\\Data\\SKSE\\Plugins\\LoreRimCampaign.ini");m_profile=value;
    m_notify=dispatcher.sink<NotifyCampaignCheckpoint>().connect<&CampaignCheckpointService::OnNotify>(this);
    m_update=dispatcher.sink<UpdateEvent>().connect<&CampaignCheckpointService::OnUpdate>(this);
    m_disconnect=dispatcher.sink<DisconnectedEvent>().connect<&CampaignCheckpointService::OnDisconnected>(this);
}
CampaignCheckpointService::~CampaignCheckpointService(){m_stop.store(true);m_wake.notify_all();if(m_worker.joinable())m_worker.join();}
void CampaignCheckpointService::Send(const std::string& body,uint64_t request)
{
    RequestCampaignCheckpoint message;message.RequestId=request?request:++m_sequence;message.Payload=body.c_str();m_transport.Send(message);
}
void CampaignCheckpointService::Fail(const std::string& reason)
{
    if(m_phase=="failed"||m_phase.empty())return;
    m_phase="failed";m_stop.store(true);m_wake.notify_all();
    Send(Json{{"action","abort"},{"proposal",m_proposal},{"reason",reason}}.dump());
    spdlog::warn("Co-op checkpoint stopped: {}",reason);
}
void CampaignCheckpointService::Resume(bool committed,const std::string& head,uint64_t revision)
{
    m_stop.store(true);m_wake.notify_all();
    if(m_setHead)m_setHead(m_generation,m_epoch.c_str(),head.c_str(),revision);
    CampaignService::CheckpointPhase(0);
    if(m_openedJournal)UI::CheckpointJournal(false);
    m_phase.clear();m_proposal.clear();m_readySent=false;m_openedJournal=false;
    spdlog::info("Co-op checkpoint {}",committed?"committed":"cancelled; previous checkpoint retained");
}
void CampaignCheckpointService::OnDisconnected(const DisconnectedEvent&) noexcept
{
    if(!m_phase.empty())Resume(false,m_parent,m_revision);
}
void CampaignCheckpointService::OnNotify(const NotifyCampaignCheckpoint& message) noexcept
{
    if(!CampaignService::IsAdmitted()||message.Payload.size()>60000)return;
    const auto body=Json::parse(message.Payload.c_str(),nullptr,false);
    if(!body.is_object()||!body.contains("phase")||!body["phase"].is_string())return;
    const auto phase=body["phase"].get<std::string>();
    if(phase=="ack")
    {
        std::lock_guard lock(m_mutex);
        if(body.value("proposal","")==m_proposal && message.RequestId==m_pending && m_pending)
        {
            const auto result=body.value("result",Json{});
            if(body.value("ok",false)&&result.is_object()&&result.value("received",uint64_t{})==m_expectedReceived)m_ack=true;
            else{m_error="Save upload was rejected";m_failed.store(true);}
            m_wake.notify_all();
        }
        return;
    }
    if(phase=="freeze")
    {
        if(!m_phase.empty()||!m_saves.is_absolute()||!m_profile.is_absolute())return;
        if(m_worker.joinable()){if(!m_done.load())return;m_worker.join();}
        m_proposal=body.value("proposal","");m_epoch=body.value("epoch","");m_parent=body.value("parent","");
        m_phase="pausing";m_started=Now();m_readySent=false;m_stop.store(false);m_failed.store(false);m_error.clear();
        auto* module=GetModuleHandleW(L"LoreRimCampaignCosave.dll");
        if(module){m_read=reinterpret_cast<CampaignSave::Read>(GetProcAddress(module,"LoreRimCampaign_Read"));m_setHead=reinterpret_cast<CampaignSave::SetHead>(GetProcAddress(module,"LoreRimCampaign_SetHead"));}
        CampaignSave::Snapshot snapshot;
        if(!m_read||!m_setHead||!m_read(&snapshot,sizeof(snapshot))||snapshot.Status!=CampaignSave::Ready){Fail("Campaign save companion is unavailable");return;}
        m_generation=snapshot.Generation;m_revision=snapshot.Record.Revision;
        CampaignService::CheckpointPhase(1);
        const auto* ui=UI::Get();m_openedJournal=ui&&!ui->GetMenuOpen(BSFixedString("Journal Menu"));
        if (ui && (ui->GetMenuOpen(BSFixedString("Dialogue Menu")) || ui->GetMenuOpen(BSFixedString("ContainerMenu"))
            || ui->GetMenuOpen(BSFixedString("BarterMenu")) || ui->GetMenuOpen(BSFixedString("Crafting Menu"))))
        { m_openedJournal=false; Fail("Close dialogue, trade and crafting menus before saving"); return; }
        if(!UI::CheckpointJournal(true))Fail("The pause menu could not be opened");
        return;
    }
    if(body.value("proposal","")!=m_proposal)return;
    if(phase=="save"&&m_phase=="paused")
    {
        m_revision=body.value("revision",uint64_t{});
        if(!m_setHead(m_generation,m_epoch.c_str(),m_proposal.c_str(),m_revision)){Fail("Loaded save changed before capture");return;}
        auto* address=m_world.ctx().at<PapyrusService>().Get("Game","SaveGame");
        if(!address){Fail("The native save service is unavailable");return;}
        // SKSE PapyrusGame.cpp: void SaveGame(StaticFunctionTag*, BSFixedString).
        // Both SDK and this string type use the non-trivial MSVC x64 value ABI.
        using SaveFunction=void (*)(void*,BSFixedString);
        const auto name="CMP_"+m_proposal;BSFixedString saveName(name.c_str());
        CampaignService::CheckpointPhase(3);m_phase="uploading";m_done.store(false);
        reinterpret_cast<SaveFunction>(const_cast<void*>(address))(nullptr,saveName);
        m_worker=std::thread(&CampaignCheckpointService::Upload,this,name,m_saves,m_profile);
    }
    if(phase=="resume")Resume(body.value("committed",false),body.value("checkpoint",m_parent),body.value("revision",m_revision));
}
void CampaignCheckpointService::OnUpdate(const UpdateEvent&) noexcept
{
    if(m_phase.empty())return;
    if(Now()>m_started+1830000){Fail("The co-op checkpoint timed out");return;}
    const auto* ui=UI::Get();
    if(!ui||!ui->GetMenuOpen(BSFixedString("Journal Menu"))||ui->numPausesGame==0)
    {if(Now()>m_started+2000)Fail("The game did not remain paused");return;}
    if(CampaignService::CheckpointUnsafe()){Fail("Game state changed while the save was sealed");return;}
    if(m_phase=="pausing"&&Now()>m_started+4000)
    {
        auto* player=PlayerCharacter::Get();
        if(!player||player->IsDead()||player->IsInCombat()){Fail("Finish combat before creating a co-op checkpoint");return;}
        if(!m_world.ctx().at<CampaignService>().CheckpointQuiet())return;
        const auto plugins=Hash(m_profile/L"plugins.txt"),mods=Hash(m_profile/L"modlist.txt");
        if(plugins.empty()||mods.empty()){Fail("The campaign profile could not be verified");return;}
        Send(Json{{"action","ready"},{"proposal",m_proposal},{"profile",{{"plugins.txt",plugins},{"modlist.txt",mods}}}}.dump());
        CampaignService::CheckpointPhase(2);m_phase="paused";m_readySent=true;
    }
    if(m_failed.load()){std::string reason;{std::lock_guard lock(m_mutex);reason=m_error;}Fail(reason.empty()?"Save upload failed":reason);return;}
    std::string upload;uint64_t request=0;
    {std::lock_guard lock(m_mutex);if(m_uploadAvailable&&(!m_pending||Now()>m_lastSend+3000))
        {if(!m_pending)m_pending=++m_sequence;request=m_pending;upload=m_uploadBody;m_lastSend=Now();}}
    if(request)Send(upload,request);
}
void CampaignCheckpointService::Upload(std::string name,std::filesystem::path saves,std::filesystem::path)
{
    auto fail=[&](const char* text){std::lock_guard lock(m_mutex);m_error=text;m_failed.store(true);m_done.store(true);};
    const std::string proposal=name.substr(4);
    const auto ess=saves/(name+".ess");const auto skse=saves/(name+".skse");
    uintmax_t previousEss=0,previousSkse=0;int stable=0;
    for(int attempt=0;attempt<1200&&!m_stop.load();++attempt)
    {
        std::error_code error;const auto sizeEss=std::filesystem::file_size(ess,error);if(error){std::this_thread::sleep_for(std::chrono::milliseconds(100));continue;}
        const auto sizeSkse=std::filesystem::file_size(skse,error);if(error){std::this_thread::sleep_for(std::chrono::milliseconds(100));continue;}
        if(sizeEss&&sizeSkse&&sizeEss==previousEss&&sizeSkse==previousSkse)++stable;else stable=0;
        previousEss=sizeEss;previousSkse=sizeSkse;
        if(stable>=10)break;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    if(m_stop.load()){m_done.store(true);return;}
    if(stable<10){fail("The save files did not finish writing");return;}
    for(const auto& [kind,path]:{std::pair<std::string,std::filesystem::path>{"ess",ess},{"skse",skse}})
    {
        const auto digest=Hash(path);std::error_code error;const auto total=std::filesystem::file_size(path,error);
        if(error||digest.empty()||!total||total>(uint64_t{2}<<30)){fail("A saved file could not be verified");return;}
        std::ifstream file(path,std::ios::binary);uint64_t offset=0;char bytes[24576];
        while(offset<total&&!m_stop.load())
        {
            file.read(bytes,static_cast<std::streamsize>(std::min<uint64_t>(sizeof(bytes),total-offset)));
            const auto count=file.gcount();if(count<=0){fail("A saved file changed during upload");return;}
            std::unique_lock lock(m_mutex);m_ack=false;m_pending=0;
            m_expectedReceived=offset+static_cast<uint64_t>(count);
            m_uploadBody=Json{{"action","upload"},{"proposal",proposal},{"kind",kind},{"offset",offset},{"total",total},{"sha256",digest},{"data",Base64(bytes,static_cast<size_t>(count))}}.dump();
            m_uploadAvailable=true;
            m_wake.wait(lock,[&]{return m_stop.load()||m_failed.load()||m_ack;});
            m_uploadAvailable=false;m_pending=0;
            if(m_stop.load()||m_failed.load()){m_done.store(true);return;}
            offset+=static_cast<uint64_t>(count);
        }
        if(m_stop.load()){m_done.store(true);return;}
        if(Hash(path)!=digest){fail("A saved file changed after upload");return;}
    }
    m_done.store(true);
}
