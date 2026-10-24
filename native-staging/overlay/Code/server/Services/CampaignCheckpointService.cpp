#include <Services/CampaignCheckpointService.h>
#include <Services/CampaignService.h>
#include <Services/InventoryService.h>
#include <Services/CalendarService.h>
#include <World.h>
#include <GameServer.h>
#include <Events/UpdateEvent.h>
#include <Events/PlayerLeaveEvent.h>
#include <Messages/NotifyCampaignCheckpoint.h>
#include <Setting.h>
#include <httplib.h>
#include <nlohmann/json.hpp>
namespace { using Json=nlohmann::json; }
CampaignCheckpointService::CampaignCheckpointService(World& world,entt::dispatcher& dispatcher):m_world(world)
{
    // Share the already configured loopback adapter port, read on the main thread.
    m_port=m_world.ctx().at<CampaignService>().ApiPort();
    m_request=dispatcher.sink<PacketEvent<RequestCampaignCheckpoint>>().connect<&CampaignCheckpointService::OnRequest>(this);
    m_update=dispatcher.sink<UpdateEvent>().connect<&CampaignCheckpointService::OnUpdate>(this);
    m_leave=dispatcher.sink<PlayerLeaveEvent>().connect<&CampaignCheckpointService::OnLeave>(this);
    m_worker=std::thread(&CampaignCheckpointService::Worker,this);
}
CampaignCheckpointService::~CampaignCheckpointService()
{
    { std::lock_guard lock(m_mutex);m_stop=true;m_jobs.clear(); }m_wake.notify_all();
    if(m_worker.joinable())m_worker.join();
}
bool CampaignCheckpointService::Queue(Job job)
{
    {std::lock_guard lock(m_mutex);if(m_jobs.size()>=32)return false;m_jobs.push_back(std::move(job));}m_wake.notify_one();return true;
}
CampaignCheckpointService::Job CampaignCheckpointService::LeaderJob(const std::string& action,const std::string& body)
{
    Job job;job.Player=m_leaderId;job.Credential=m_leaderCredential;job.Action=action;job.Body=body;return job;
}
void CampaignCheckpointService::Broadcast(const std::string& body)
{
    NotifyCampaignCheckpoint notify;notify.Payload=body.c_str();
    for(auto* player:m_world.GetPlayerManager())
        if(m_world.ctx().at<CampaignService>().IsAdmitted(player))player->Send(notify);
}
void CampaignCheckpointService::Abort(const std::string& reason)
{
    if(!IsPreparing())return;
    m_abortReason=reason;
    if(m_controlPending)return;
    m_controlPending=Queue(LeaderJob("abort",Json{{"proposal",m_proposal},{"reason",reason}}.dump()));
}
void CampaignCheckpointService::OnLeave(const PlayerLeaveEvent& event) noexcept
{
    if(IsPreparing())Abort("A player disconnected during the checkpoint");
    m_frozenPeers.erase(event.pPlayer->GetId());
}
void CampaignCheckpointService::OnRequest(const PacketEvent<RequestCampaignCheckpoint>& event) noexcept
{
    const auto& request=event.Packet;
    auto& campaign=m_world.ctx().at<CampaignService>();
    if(!campaign.IsAdmitted(event.pPlayer)||!request.RequestId||request.Payload.size()>60000)return;
    const auto body=Json::parse(request.Payload.c_str(),nullptr,false);
    if(!body.is_object()||!body.contains("proposal")||!body["proposal"].is_string()||!body.contains("action")||!body["action"].is_string()
        ||body.value("proposal","")!=m_proposal||!IsPreparing())return;
    const auto action=body.value("action","");
    if(action!="ready"&&action!="upload"&&action!="abort")return;
    if(action=="ready")m_frozenPeers.insert(event.pPlayer->GetId());
    Job job;job.Player=event.pPlayer->GetId();job.Connection=event.pPlayer->GetConnectionId();job.Request=request.RequestId;
    job.Credential=campaign.CredentialFor(event.pPlayer);job.Action=action;job.Body=body.dump();
    if(!Queue(std::move(job)))Abort("Checkpoint upload queue was full");
}
void CampaignCheckpointService::ApplyStatus(const std::string& text)
{
    const auto body=Json::parse(text,nullptr,false);
    if(!body.is_object()||!body.contains("state")||body.value("state","")=="idle")return;
    const auto id=body.value("id","");const auto state=body.value("state","");
    if(id.empty())return;
    if(id!=m_proposal)
    {
        if(state=="committed"||state=="aborted")return;
        m_proposal=id;m_phase="requested";m_epoch=body.value("epoch","");m_parent=body.value("parent",Json{}).is_string()?body["parent"].get<std::string>():"";
        m_revision=body.value("revision",uint64_t{});m_frozenPeers.clear();
        if(m_world.ctx().at<InventoryService>().HasActiveDrops()){Abort("Pick up shared dropped items before making a co-op checkpoint");return;}
        Broadcast(Json{{"phase","freeze"},{"proposal",id},{"epoch",m_epoch},{"parent",m_parent}}.dump());
    }
    if(state=="committed"||state=="aborted")
    {
        if(m_phase!=state)
        {
            Broadcast(Json{{"phase","resume"},{"proposal",id},{"committed",state=="committed"},{"epoch",m_epoch},
                {"checkpoint",state=="committed"?id:m_parent},{"revision",body.value("revision",m_revision)},{"reason",body.value("failure","")}}.dump());
            m_frozenPeers.clear();m_abortReason.clear();m_phase=state;
        }
        return;
    }
    if(state=="saving")
    {
        if(m_phase!="saving")
        {
            m_phase="saving";m_revision=body.value("revision",uint64_t{});
            m_world.ctx().at<CalendarService>().SendCheckpointTime();
            Broadcast(Json{{"phase","save"},{"proposal",id},{"epoch",m_epoch},{"revision",m_revision}}.dump());
        }
        bool complete=body.contains("uploads")&&body["uploads"].is_array()&&body.contains("peers")&&body["peers"].is_array()
            &&body["uploads"].size()==body["peers"].size()*2;
        if(complete)for(const auto& file:body["uploads"])if(!file.value("verified",0))complete=false;
        if(complete&&!m_controlPending)m_controlPending=Queue(LeaderJob("commit",Json{{"proposal",id}}.dump()));
        return;
    }
    bool ready=body.contains("peers")&&body["peers"].is_array()&&!body["peers"].empty();
    if(ready)for(const auto& peer:body["peers"])if(!peer.value("ready",0))ready=false;
    if(ready&&!m_controlPending&&!m_world.ctx().at<CampaignService>().HasPendingWorldChanges())
        m_controlPending=Queue(LeaderJob("seal",Json{{"proposal",id}}.dump()));
}
void CampaignCheckpointService::OnUpdate(const UpdateEvent&) noexcept
{
    if(!CampaignService::IsRequired())return;
    const uint64_t now=GameServer::Get()->GetTick();
    for(auto* player:m_world.GetPlayerManager())
        if(m_world.ctx().at<CampaignService>().CanQuest(player))
        {m_leaderId=player->GetId();m_leaderCredential=m_world.ctx().at<CampaignService>().CredentialFor(player);break;}
    if(now>=m_nextPoll&&!m_pollPending&&!m_leaderCredential.empty())
    {m_nextPoll=now+1000;m_pollPending=Queue(LeaderJob("status","{}"));}
    std::deque<Result> ready;{std::lock_guard lock(m_mutex);ready.swap(m_results);}
    for(auto& result:ready)
    {
        if(result.Work.Action=="status")m_pollPending=false;
        if(result.Work.Action=="seal"||result.Work.Action=="commit"||result.Work.Action=="abort")m_controlPending=false;
        if(result.Work.Request)
        {
            if(auto* player=m_world.GetPlayerManager().GetById(result.Work.Player))
                if(player->GetConnectionId()==result.Work.Connection&&m_world.ctx().at<CampaignService>().IsAdmitted(player))
                {
                    NotifyCampaignCheckpoint notify;notify.RequestId=result.Work.Request;
                    const auto parsed=Json::parse(result.Body,nullptr,false);
                    notify.Payload=Json{{"phase","ack"},{"proposal",m_proposal},{"ok",result.Ok},{"result",parsed.is_discarded()?Json{}:parsed}}.dump().c_str();player->Send(notify);
                }
            if(!result.Ok)Abort("A client checkpoint request failed verification");
        }
        if(!result.Ok&&(result.Work.Action=="seal"||result.Work.Action=="commit"))Abort("The checkpoint could not be committed; previous checkpoint retained");
        if(result.Ok&&(result.Work.Action=="status"||result.Work.Action=="seal"))ApplyStatus(result.Body);
        if(!m_abortReason.empty()&&!m_controlPending&&result.Work.Action!="abort")Abort(m_abortReason);
        if(result.Ok&&(result.Work.Action=="commit"||result.Work.Action=="abort"))
            if(!m_pollPending)m_pollPending=Queue(LeaderJob("status",Json{{"proposal",m_proposal}}.dump()));
    }
}
void CampaignCheckpointService::Worker()
{
    for(;;)
    {
        Job job;{std::unique_lock lock(m_mutex);m_wake.wait(lock,[&]{return m_stop||!m_jobs.empty();});if(m_stop)return;job=std::move(m_jobs.front());m_jobs.pop_front();}
        Result result;result.Work=job;
        try
        {
            httplib::Client client("127.0.0.1",m_port);client.set_connection_timeout(0,500000);client.set_read_timeout(5,0);client.set_write_timeout(2,0);
            client.set_default_headers({{"Authorization","Bearer "+job.Credential}});
            const auto response=client.Post(("/v1/coopsave/"+job.Action).c_str(),job.Body,"application/json");
            if(response&&response->body.size()<1048576){result.Ok=response->status==200;result.Body=response->body;}
        }
        catch(...){result.Ok=false;}
        {std::lock_guard lock(m_mutex);if(!m_stop)m_results.push_back(std::move(result));}
    }
}
