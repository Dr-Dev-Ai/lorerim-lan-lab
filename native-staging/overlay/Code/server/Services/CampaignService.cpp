#include <Services/CampaignService.h>
#include <Services/CharacterService.h>
#include <Services/CampaignCheckpointService.h>
#include <Messages/NotifyCampaignFollower.h>
#include <Messages/NotifyPlayerJoined.h>
#include <Events/PlayerJoinEvent.h>
#include <cctype>
#include <World.h>
#include <GameServer.h>
#include <Events/UpdateEvent.h>
#include <Events/PlayerLeaveEvent.h>
#include <Setting.h>
#include <httplib.h>
#include <nlohmann/json.hpp>
#include <iomanip>
#include <sstream>

namespace
{
Console::Setting bEnableCampaignGuard{"Gameplay:bEnableCampaignGuard", "Experimental persistent campaign interaction guard", false};
Console::Setting uCampaignApiPort{"Gameplay:uCampaignApiPort", "Local campaign manager API port", 10579u};
using Json = nlohmann::json;
}
bool CampaignService::IsRequired() noexcept { return bEnableCampaignGuard; }
CampaignService::CampaignService(World& world, entt::dispatcher& dispatcher) : m_world(world), m_apiPort(static_cast<int>(uCampaignApiPort.value_as<uint32_t>()))
{
    m_requestConnection = dispatcher.sink<PacketEvent<CampaignActionRequest>>().connect<&CampaignService::OnRequest>(this);
    m_updateConnection = dispatcher.sink<UpdateEvent>().connect<&CampaignService::OnUpdate>(this);
    m_leaveConnection = dispatcher.sink<PlayerLeaveEvent>().connect<&CampaignService::OnLeave>(this);
    m_worker = std::thread(&CampaignService::Worker, this);
}
CampaignService::~CampaignService()
{
    { std::lock_guard lock(m_mutex); m_stop = true; m_jobs.clear(); }
    m_wake.notify_one();
    if (m_worker.joinable()) m_worker.join();
}
std::string CampaignService::ActorKey(const GameId& id) const
{
    if (!id || id.ModId == 0xffffffffu || id.BaseId > 0xffffffu) return {};
    const auto& mods = m_world.ctx().at<ModsComponent>();
    auto find = [&](const auto& entries) -> std::string
    {
        for (const auto& [name, entry] : entries)
            if (entry.id == id.ModId)
            {
                std::ostringstream out;
                out << name.c_str() << '|' << std::hex << std::setw(6) << std::setfill('0') << id.BaseId;
                std::string key = out.str();
                std::transform(key.begin(), key.end(), key.begin(), [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
                return key;
            }
        return {};
    };
    std::string key = find(mods.GetStandardMods());
    return key.empty() ? find(mods.GetLiteMods()) : key;
}
bool CampaignService::CanClaimFollower(const Player* player, const GameId& actor) const noexcept
{
    if (!IsRequired()) return true;
    const auto policy = m_followers.find(ActorKey(actor));
    if (policy == m_followers.end() || policy->second.State == "dismissed") return true;
    const auto session = m_sessions.find(player->GetId());
    return session != m_sessions.end() && session->second.Attached
        && session->second.Expires > GameServer::Get()->GetTick()
        && session->second.StablePlayer == policy->second.Owner;
}
void CampaignService::ReconcileFollowers(uint64_t now)
{
    if (!IsRequired() || m_world.ctx().at<CampaignCheckpointService>().IsPreparing() || now < m_nextFollowerReconcile) return;
    m_nextFollowerReconcile = now + 2000;
    auto view = m_world.view<FormIdComponent, CharacterComponent, OwnerComponent, CellIdComponent>();
    for (auto entity : view)
    {
        const auto& character = view.get<CharacterComponent>(entity);
        if (character.IsPlayer() || character.IsMount() || character.IsDead()) continue;
        const auto& form = view.get<FormIdComponent>(entity).Id;
        const auto known = m_followers.find(ActorKey(form));
        if (known == m_followers.end() || known->second.State == "dead" || known->second.State == "dismissed") continue;
        const auto& policy = known->second;
        Player* recruiter = nullptr;
        if (!policy.Parked && policy.Until > now)
            for (const auto& [id, session] : m_sessions)
                if (session.Attached && session.Expires > now && session.StablePlayer == policy.Owner)
                {
                    auto* candidate = m_world.GetPlayerManager().GetById(id);
                    if (candidate && candidate->GetCellComponent().IsInRange(view.get<CellIdComponent>(entity), character.IsDragon())) recruiter = candidate;
                    break;
                }
        auto& ownership = view.get<OwnerComponent>(entity);
        if (recruiter && ownership.GetOwner() != recruiter)
            if (!m_world.ctx().at<CharacterService>().TransferCampaignFollower(recruiter, entity)) recruiter = nullptr;
        if (auto* simulator = ownership.GetOwner())
        {
            NotifyCampaignFollower notify;
            notify.Actor = form; notify.OwnershipEpoch = ownership.OwnershipEpoch;
            notify.Sequence = ++m_followerSequence;
            notify.Policy = !recruiter ? 1 : (policy.State == "waiting" ? 3 : 2);
            simulator->Send(notify);
        }
    }
}
std::string CampaignService::CredentialFor(const Player* player) const
{
    const auto session = m_sessions.find(player->GetId());
    return session != m_sessions.end() && IsAdmitted(player) ? session->second.Credential : std::string{};
}
void CampaignService::NoteWorldChange() noexcept
{
    if (IsRequired()) { ++m_worldSerial; m_worldChangePending = true; }
}
bool CampaignService::IsAdmitted(const Player* player) const noexcept
{
    if (!IsRequired()) return true;
    const auto session = m_sessions.find(player->GetId());
    return session != m_sessions.end() && session->second.Attached && session->second.Expires > GameServer::Get()->GetTick();
}
void CampaignService::StageJoin(Player* player, const GameId& world, const GameId& cell, const DateTime& time)
{
    m_pendingJoins[player->GetId()] = {world, cell, time};
}
void CampaignService::CompleteJoin(Player* player)
{
    const auto pending = m_pendingJoins.find(player->GetId());
    if (pending == m_pendingJoins.end()) return;
    for (auto* other : m_world.GetPlayerManager())
    {
        if (other == player || !IsAdmitted(other)) continue;
        NotifyPlayerJoined joined;
        joined.PlayerId = other->GetId(); joined.Username = other->GetUsername(); joined.Level = other->GetLevel();
        joined.WorldSpaceId = other->GetCellComponent().WorldSpaceId; joined.CellId = other->GetCellComponent().Cell;
        player->Send(joined);
    }
    const auto state = pending->second; m_pendingJoins.erase(pending);
    m_world.GetDispatcher().trigger(PlayerJoinEvent(player, state.WorldSpace, state.Cell, state.Time));
}
bool CampaignService::CanQuest(const Player* player) const noexcept
{
    if (!IsRequired()) return true;
    const auto it = m_sessions.find(player->GetId());
    return it != m_sessions.end() && it->second.Attached && it->second.Expires > GameServer::Get()->GetTick() && it->second.Leader;
}
bool CampaignService::CanInteract(const Player* player, const GameId& actor) const noexcept
{
    if (!IsRequired()) return true;
    const auto session = m_sessions.find(player->GetId());
    if (session == m_sessions.end() || !session->second.Attached || session->second.Expires <= GameServer::Get()->GetTick()) return false;
    const auto it = m_grants.find(ActorKey(actor));
    return it != m_grants.end() && it->second.Player == player->GetId() && it->second.Expires > GameServer::Get()->GetTick();
}
bool CampaignService::Queue(Job job)
{
    { std::lock_guard lock(m_mutex);
      if (job.Disconnect)
      {
          // Closing a connection takes priority over its abandoned interaction work.
          std::erase_if(m_jobs, [&](const Job& pending) { return !pending.WorldChange && pending.SessionKey == job.SessionKey; });
          if (m_jobs.size() >= 64) m_jobs.pop_back();
          m_jobs.push_front(std::move(job));
      }
      else { if (m_jobs.size() >= 64) return false; m_jobs.push_back(std::move(job)); } }
    m_wake.notify_one();
    return true;
}
void CampaignService::OnRequest(const PacketEvent<CampaignActionRequest>& event) noexcept
{
    const auto& request = event.Packet;
    NotifyCampaignAction denied;
    denied.RequestId = request.RequestId;
    denied.Actor = request.Actor;
    denied.Action = request.Action;
    denied.Enabled = IsRequired();
    if (!IsRequired() || !request.RequestId || static_cast<uint8_t>(request.Action) > static_cast<uint8_t>(CampaignAction::FollowerSeenWaiting))
    { event.pPlayer->Send(denied); return; }
    Job job;
    job.Player = event.pPlayer->GetId();
    job.Request = request;
    if (request.Action == CampaignAction::Join)
    {
        if (m_worldChangePending || m_worldChangeQueued) { event.pPlayer->Send(denied); return; }
        if (request.Credential.empty() || request.Credential.size() > 128 || request.SaveProof.empty() || request.SaveProof.size() > 2048 || m_sessions.contains(job.Player))
        { event.pPlayer->Send(denied); return; }
        job.Credential.assign(request.Credential.c_str());
        for (const auto& [id, session] : m_sessions)
            if (session.Credential == job.Credential) { event.pPlayer->Send(denied); return; }
        // Reserve attach while asynchronous authentication is running.
        job.SessionKey = std::to_string(std::chrono::system_clock::now().time_since_epoch().count()) + "-" + std::to_string(job.Player);
        Session session;
        session.Credential = job.Credential; session.LatestRequest = request.RequestId; session.Key = job.SessionKey;
        m_sessions[job.Player] = std::move(session);
    }
    else
    {
        const auto session = m_sessions.find(job.Player);
        job.ActorKey = ActorKey(request.Actor);
        if (session == m_sessions.end() || !session->second.Attached || session->second.Expires <= GameServer::Get()->GetTick() || job.ActorKey.empty() || request.RequestId <= session->second.LatestRequest)
        { event.pPlayer->Send(denied); return; }
        session->second.LatestRequest = request.RequestId;
        if (request.Action < CampaignAction::FollowerClaim) session->second.LatestDialogue = request.RequestId;
        job.Credential = session->second.Credential;
        job.SessionKey = session->second.Key;
        // Only synced, visible NPC references may acquire interaction grants.
        bool visible = false;
        auto view = m_world.view<FormIdComponent, CharacterComponent, CellIdComponent>();
        for (const auto entity : view)
            if (view.get<FormIdComponent>(entity).Id == request.Actor && !view.get<CharacterComponent>(entity).IsPlayer()
                && event.pPlayer->GetCellComponent().IsInRange(view.get<CellIdComponent>(entity), false)) { visible = true; break; }
        if (!visible) { event.pPlayer->Send(denied); return; }
        if (request.Action == CampaignAction::Renew || request.Action == CampaignAction::Release)
        {
            const auto grant = m_grants.find(job.ActorKey);
            if (grant == m_grants.end() || grant->second.Player != job.Player)
            { event.pPlayer->Send(denied); return; }
            job.LeaseToken = grant->second.Token;
            job.Generation = grant->second.Generation;
        }
    }
    if (!Queue(std::move(job))) { if (request.Action == CampaignAction::Join) m_sessions.erase(event.pPlayer->GetId()); event.pPlayer->Send(denied); }
}
void CampaignService::OnLeave(const PlayerLeaveEvent& event) noexcept
{
    const uint32_t id = event.pPlayer->GetId();
    m_pendingJoins.erase(id);
    const auto it = m_sessions.find(id);
    if (it != m_sessions.end())
    {
        Job job; job.Player = id; job.Credential = it->second.Credential; job.SessionKey = it->second.Key; job.Disconnect = true;
        Queue(std::move(job));
        m_sessions.erase(it);
    }
    for (auto grant = m_grants.begin(); grant != m_grants.end();)
        if (grant->second.Player == id) grant = m_grants.erase(grant); else ++grant;
}
void CampaignService::OnUpdate(const UpdateEvent&) noexcept
{
    const uint64_t now = GameServer::Get()->GetTick();
    for (auto& [id, session] : m_sessions)
    {
        if (session.Attached && session.Expires <= now)
        {
            session.Attached = false;
            Job close; close.Player = id; close.Credential = session.Credential;
            close.SessionKey = session.Key; close.Disconnect = true;
            Queue(std::move(close));
            if (auto* player = m_world.GetPlayerManager().GetById(id))
            {
                NotifyCampaignAction expired; expired.Enabled = true; expired.Action = CampaignAction::SessionExpired;
                player->Send(expired);
            }
        }
        if (!session.Attached || now < session.NextHeartbeat) continue;
        Job heartbeat; heartbeat.Player = id; heartbeat.Credential = session.Credential;
        heartbeat.SessionKey = session.Key; heartbeat.Heartbeat = true;
        if (Queue(std::move(heartbeat))) session.NextHeartbeat = now + 10000;
    }
    if (m_worldChangePending && !m_worldChangeQueued && now >= m_nextWorldRetry)
        for (const auto& [id, session] : m_sessions)
            if (session.Attached)
            {
                Job marker; marker.Player = id; marker.Credential = session.Credential; marker.SessionKey = session.Key; marker.WorldChange = true; marker.WorldSerial = m_worldSerial;
                marker.Operation = "world-" + session.Key + "-" + std::to_string(marker.WorldSerial);
                if (Queue(std::move(marker))) { m_worldChangeQueued = true; m_nextWorldRetry = now + 250; }
                break;
            }
    std::deque<Result> ready;
    { std::lock_guard lock(m_mutex); ready.swap(m_results); }
    for (auto& result : ready)
    {
        if (result.Work.WorldChange)
        {
            m_worldChangeQueued = false;
            if (result.Allowed) m_worldPersistedSerial = std::max(m_worldPersistedSerial, result.Work.WorldSerial);
            else m_nextWorldRetry = now + 1000;
            m_worldChangePending = m_worldSerial > m_worldPersistedSerial;
            continue;
        }
        Player* player = m_world.GetPlayerManager().GetById(result.Work.Player);
        const auto session = m_sessions.find(result.Work.Player);
        if (!player || session == m_sessions.end() || session->second.Key != result.Work.SessionKey) continue;
        if (result.Allowed && (result.Work.Heartbeat || result.Work.Request.Action != CampaignAction::Join || m_campaign.empty() || m_campaign == result.Campaign))
            for (auto& follower : result.Followers)
            {
                const auto old = m_followers.find(follower.Actor);
                if (old == m_followers.end() || old->second.Version <= follower.Version)
                {
                    follower.Until = now + 35000;
                    m_followers[follower.Actor] = std::move(follower);
                }
            }
        if (result.Work.Heartbeat)
        {
            if (result.Allowed && session->second.Attached)
            {
                session->second.Expires = now + 35000;
                NotifyCampaignAction state; state.Enabled = state.Allowed = true; state.Action = CampaignAction::SessionState;
                state.Epoch = result.Epoch.c_str(); state.Checkpoint = result.Checkpoint.c_str(); state.Revision = result.Revision;
                player->Send(state);
            }
            // Failed heartbeats never extend authority; queued grants expire independently.
            continue;
        }
        if (session->second.Credential != result.Work.Credential || (result.Work.Request.Action < CampaignAction::FollowerClaim && (result.Work.Request.Action == CampaignAction::Join ? session->second.LatestRequest : session->second.LatestDialogue) != result.Work.Request.RequestId)) continue;
        const auto action = result.Work.Request.Action;
        if (action == CampaignAction::Join)
        {
            if (result.Allowed && ((!m_campaign.empty() && m_campaign != result.Campaign) || m_worldChangePending || m_worldChangeQueued))
            {
                result.Allowed = false;
                Job close; close.Player = result.Work.Player; close.Credential = result.Work.Credential;
                close.SessionKey = result.Work.SessionKey; close.Disconnect = true; Queue(std::move(close));
            }
            if (result.Allowed)
            {
                m_campaign = result.Campaign;
                session->second.StablePlayer = result.StablePlayer; session->second.Campaign = result.Campaign;
            }
            if (result.Allowed) { session->second.Leader = result.Leader; session->second.Attached = true; session->second.Expires = now + 35000; session->second.NextHeartbeat = now + 10000; }
            else m_sessions.erase(session);
        }
        else if (result.Allowed && (action == CampaignAction::Acquire || action == CampaignAction::Renew))
            m_grants[result.Work.ActorKey] = {result.Work.Player, GameServer::Get()->GetTick() + 20000, result.LeaseToken, result.Generation};
        else if (action == CampaignAction::Release)
            m_grants.erase(result.Work.ActorKey);
        NotifyCampaignAction notify;
        notify.RequestId = result.Work.Request.RequestId; notify.Actor = result.Work.Request.Actor; notify.Action = action;
        notify.Enabled = true; notify.Allowed = result.Allowed; notify.IsLeader = result.Leader;
        notify.Epoch = result.Epoch.c_str(); notify.Checkpoint = result.Checkpoint.c_str(); notify.Revision = result.Revision;
        player->Send(notify);
        if (action == CampaignAction::Join && result.Allowed) CompleteJoin(player);
    }
    ReconcileFollowers(now);
}
void CampaignService::Worker()
{
    for (;;)
    {
        Job job;
        { std::unique_lock lock(m_mutex); m_wake.wait(lock, [&] { return m_stop || !m_jobs.empty(); });
          if (m_stop) return; job = std::move(m_jobs.front()); m_jobs.pop_front(); }
        Result result; result.Work = job;
        try
        {
            httplib::Client client("127.0.0.1", m_apiPort);
            client.set_connection_timeout(0, 500000); client.set_read_timeout(1, 0); client.set_write_timeout(1, 0);
            client.set_default_headers({{"Authorization", "Bearer " + job.Credential}});
            auto post = [&](const char* path, const Json& body) -> Json
            {
                auto response = client.Post(path, body.dump(), "application/json");
                if (!response || response->status != 200 || response->body.size() > 1048576) return {};
                return Json::parse(response->body, nullptr, false);
            };
            if (job.Disconnect)
            {
                post("/v1/session/close", {{"session", job.SessionKey}});
                continue;
            }
            Json response;
            if (job.WorldChange)
            {
                response = post("/v1/world/dirty", {{"operation", job.Operation}});
                result.Allowed = response.is_object() && response.value("recorded", false);
            }
            else if (job.Heartbeat)
            {
                response = post("/v1/session/heartbeat", {{"session", job.SessionKey}});
                result.Allowed = response.is_object() && response.value("attached", false);
                if (result.Allowed)
                {
                    result.Epoch = response.value("epoch", ""); result.Checkpoint = response.value("checkpoint", "");
                    result.Revision = response.value("revision", uint64_t{});
                }
            }
            else if (job.Request.Action == CampaignAction::Join)
            {
                response = post("/v1/me", Json::object());
                if (response.is_object() && response.contains("is_leader"))
                {
                    result.Leader = response.value("is_leader", false);
                    result.StablePlayer = response.value("player", ""); result.Campaign = response.value("campaign", "");
                    const auto proof = Json::parse(job.Request.SaveProof.c_str(), nullptr, false);
                    const auto present = proof.is_object() ? post("/v1/session/open", {{"session", job.SessionKey}, {"proof", proof}}) : Json{};
                    if (present.is_object())
                    {
                        result.Epoch = present.value("epoch", ""); result.Checkpoint = present.value("checkpoint", "");
                        result.Revision = present.value("revision", uint64_t{});
                    }
                    result.Allowed = present.is_object() && present.contains("revision");
                }
            }
            else if (job.Request.Action >= CampaignAction::FollowerClaim)
            {
                if (job.Request.Action == CampaignAction::FollowerPermission)
                {
                    response = post("/v1/permission", {{"actor", job.ActorKey}, {"action", "command"}});
                    result.Allowed = response.is_object() && response.value("allowed", false);
                }
                else
                {
                    const char* state = "claim";
                    switch (job.Request.Action)
                    {
                    case CampaignAction::FollowerFollow: state = "following"; break;
                    case CampaignAction::FollowerWait: state = "waiting"; break;
                    case CampaignAction::FollowerDismiss: state = "dismissed"; break;
                    case CampaignAction::FollowerDead: state = "dead"; break;
                    case CampaignAction::FollowerSeen: state = "seen"; break;
                    case CampaignAction::FollowerSeenWaiting: state = "seen_waiting"; break;
                    default: break;
                    }
                    response = post("/v1/followers/observe", {{"actor", job.ActorKey}, {"state", state},
                        {"operation", "native-follower-" + std::to_string(job.Player) + "-" + std::to_string(job.Request.RequestId) + "-" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count())}});
                    result.Allowed = response.is_object() && response.contains("owner");
                }
            }
            else if (job.Request.Action == CampaignAction::Acquire)
            {
                response = post("/v1/dialogue/acquire", {{"actor", job.ActorKey}, {"action", "talk"}});
                result.Allowed = response.is_object() && response.contains("token") && response.contains("generation");
            }
            else
            {
                response = post(job.Request.Action == CampaignAction::Renew ? "/v1/dialogue/renew" : "/v1/dialogue/release",
                                {{"actor", job.ActorKey}, {"token", job.LeaseToken}, {"generation", job.Generation}});
                result.Allowed = response.is_object() && (response.contains("expires") || response.value("released", false));
            }
            auto readFollower = [&](const Json& row)
            {
                if (!row.is_object()) return;
                const auto metadata = Json::parse(row.value("metadata", "{}"), nullptr, false);
                if (!metadata.is_object() || metadata.value("adapter", "") != "sff") return;
                FollowerPolicy policy;
                policy.Actor = row.value("actor", ""); policy.Owner = row.value("owner", "");
                policy.State = row.value("state", ""); policy.Version = row.value("version", uint64_t{});
                policy.Parked = row.value("parked", 1) != 0;
                if (!policy.Actor.empty() && !policy.Owner.empty() && policy.Version
                    && (policy.State == "following" || policy.State == "waiting" || policy.State == "dismissed" || policy.State == "dead")) result.Followers.push_back(std::move(policy));
            };
            if (result.Allowed && (job.Heartbeat || (!job.WorldChange && job.Request.Action == CampaignAction::Join)))
            {
                const auto snapshot = post("/v1/followers/policies", Json::object());
                if (snapshot.is_object() && snapshot.contains("followers") && snapshot["followers"].is_array() && snapshot["followers"].size() <= 128)
                {
                    for (const auto& row : snapshot["followers"]) readFollower(row);
                    result.FollowerSnapshot = true;
                }
            }
            else if (result.Allowed && job.Request.Action >= CampaignAction::FollowerClaim) readFollower(response);
            if (result.Allowed && response.is_object() && response.contains("token"))
            { result.LeaseToken = response.at("token").get<std::string>(); result.Generation = response.at("generation").get<uint64_t>(); }
        }
        catch (...) { result.Allowed = false; } // Fail closed without exposing credentials or metadata.
        { std::lock_guard lock(m_mutex); if (!m_stop && m_results.size() < 64) m_results.push_back(std::move(result)); }
    }
}
